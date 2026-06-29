from __future__ import annotations

from decimal import Decimal
from itertools import cycle
from uuid import UUID

from pydantic import ValidationError

from creativity_layer.budget import (
    BudgetController,
    BudgetExceeded,
    BudgetReservation,
)
from creativity_layer.models import (
    FramedTask,
    IdeaGenome,
    RunConfig,
    RunError,
    RunProviders,
    RunResult,
    TaskContext,
)
from creativity_layer.operation import (
    provider_identity,
    validate_evaluation_payload,
    validate_framing_payload,
    validate_metered_envelope,
    validate_quote,
    validate_seed_payload,
    validate_transform_payload,
)
from creativity_layer.population import PopulationManager
from creativity_layer.providers import (
    IdeaEvaluator,
    IdeaSeeder,
    IdeaTransformer,
    MeteredResponse,
    OperationQuote,
    TaskFramer,
)
from creativity_layer.transforms import OperatorName, TransformationRequest

OPERATOR_SCHEDULE = (
    OperatorName.INVERT,
    OperatorName.REFRAME,
    OperatorName.SUBTRACT,
    OperatorName.CONTRADICT,
)


def _exceeds_quote(response: MeteredResponse[object], quote: OperationQuote) -> bool:
    return Decimal(str(response.cost_usd)) > Decimal(str(quote.max_cost_usd))


def _error(
    errors: list[RunError],
    *,
    stage: str,
    provider: str,
    category: str,
    message: str,
    cost_incurred: bool,
) -> None:
    errors.append(
        RunError(
            stage=stage,
            provider=provider,
            category=category,
            message=message,
            cost_incurred=cost_incurred,
        )
    )


def _validated_candidate(
    candidate: IdeaGenome,
    *,
    scores: object | None = None,
    branch_cost: Decimal,
    branch_latency: Decimal,
) -> IdeaGenome:
    payload = candidate.model_dump(mode="python")
    if scores is not None:
        payload["scores"] = scores
    payload["branch_cost_usd"] = float(branch_cost)
    payload["branch_latency_ms"] = float(branch_latency)
    return IdeaGenome.model_validate(payload)


class CreativeEngine:
    def __init__(
        self,
        *,
        framer: TaskFramer,
        seeder: IdeaSeeder,
        transformer: IdeaTransformer,
        evaluator: IdeaEvaluator,
        population: PopulationManager | None = None,
    ) -> None:
        self._framer = framer
        self._seeder = seeder
        self._transformer = transformer
        self._evaluator = evaluator
        self._population = population or PopulationManager()
        self._providers = RunProviders(
            framer=provider_identity(framer),
            seeder=provider_identity(seeder),
            transformer=provider_identity(transformer),
            evaluator=provider_identity(evaluator),
        )

    def run(self, task: TaskContext, config: RunConfig) -> RunResult:
        budget = BudgetController(config)
        errors: list[RunError] = []
        providers = self._providers
        framed, stopped_reason = self._frame(
            task,
            budget,
            errors,
            providers,
        )
        if stopped_reason is not None:
            return self._result(
                framed, (), budget, config, providers, errors, stopped_reason
            )

        candidates, stopped_reason = self._seed_and_evaluate(
            framed,
            config,
            budget,
            errors,
            providers,
        )
        if stopped_reason is not None:
            return self._result(
                framed,
                tuple(candidates),
                budget,
                config,
                providers,
                errors,
                stopped_reason,
            )

        all_candidates = list(candidates)
        candidate_ids = {candidate.id for candidate in candidates}
        current_generation = tuple(candidates)
        attempted: set[tuple[tuple[UUID, ...], OperatorName]] = set()
        operators = cycle(OPERATOR_SCHEDULE)

        for _generation in range(config.max_generations):
            parents = self._population.select(
                current_generation,
                finalist_count=min(config.seed_count, len(current_generation)),
            )
            descendants: list[IdeaGenome] = []

            for parent in parents:
                operator = next(operators)
                operation = ((parent.id,), operator)
                if operation in attempted:
                    continue
                attempted.add(operation)
                request = TransformationRequest.for_operator(
                    operator=operator,
                    parents=(parent,),
                    task_goal=task.goal,
                )
                descendant, stopped_reason = self._transform_and_evaluate(
                    request,
                    (parent,),
                    framed,
                    budget,
                    candidate_ids,
                    errors,
                    providers,
                )
                if descendant is not None:
                    descendants.append(descendant)
                    all_candidates.append(descendant)
                    candidate_ids.add(descendant.id)
                if stopped_reason is not None:
                    return self._result(
                        framed,
                        tuple(all_candidates),
                        budget,
                        config,
                        providers,
                        errors,
                        stopped_reason,
                    )

            if descendants:
                current_generation = tuple(descendants)

        return self._result(
            framed,
            tuple(all_candidates),
            budget,
            config,
            providers,
            errors,
            "generation_limit",
        )

    def _frame(
        self,
        task: TaskContext,
        budget: BudgetController,
        errors: list[RunError],
        providers: RunProviders,
    ) -> tuple[FramedTask, str | None]:
        try:
            quote = validate_quote(self._framer.quote_frame(task))
        except Exception:
            _error(
                errors,
                stage="framing",
                provider=providers.framer.name,
                category="quote_error",
                message="provider quote failed validation",
                cost_incurred=False,
            )
            return self._fallback_framed_task(task), "provider_error"

        try:
            reservation = budget.reserve_for_framing(
                quote.max_cost_usd,
                required_calls=quote.calls,
            )
        except BudgetExceeded:
            _error(
                errors,
                stage="framing",
                provider=providers.framer.name,
                category="budget_error",
                message="insufficient budget for framing",
                cost_incurred=False,
            )
            return self._fallback_framed_task(task), "budget_exhausted"

        with reservation:
            try:
                response = validate_metered_envelope(self._framer.frame(task))
            except ValidationError:
                self._charge_attempt_from_quote(
                    quote,
                    reservation,
                    stage="framing",
                    provider=providers.framer.name,
                )
                _error(
                    errors,
                    stage="framing",
                    provider=providers.framer.name,
                    category="validation_error_after_response",
                    message="provider returned invalid metered response",
                    cost_incurred=True,
                )
                return self._fallback_framed_task(task), "provider_error"
            except Exception:
                self._charge_attempt_from_quote(
                    quote,
                    reservation,
                    stage="framing",
                    provider=providers.framer.name,
                )
                _error(
                    errors,
                    stage="framing",
                    provider=providers.framer.name,
                    category="provider_error_after_attempt",
                    message="provider operation failed after invocation",
                    cost_incurred=True,
                )
                return self._fallback_framed_task(task), "provider_error"

            if not self._charge_response(
                response,
                quote,
                reservation,
                budget,
                stage="framing",
                expected_provider=providers.framer.name,
                errors=errors,
            ):
                return self._fallback_framed_task(task), "provider_error"

            try:
                framed = validate_framing_payload(response)
            except ValidationError:
                _error(
                    errors,
                    stage="framing",
                    provider=providers.framer.name,
                    category="validation_error_after_response",
                    message="provider returned invalid framed task",
                    cost_incurred=True,
                )
                return self._fallback_framed_task(task), "provider_error"

        budget.release_framing_reserve()
        return framed, None

    @staticmethod
    def _charge_attempt_from_quote(
        quote: OperationQuote,
        reservation: BudgetReservation,
        *,
        stage: str,
        provider: str,
    ) -> None:
        reservation.charge(
            stage,
            provider,
            quote.max_cost_usd,
            0,
            cost_is_estimated=True,
            calls=quote.calls,
        )

    @staticmethod
    def _fallback_framed_task(task: TaskContext) -> FramedTask:
        return FramedTask(
            context=task,
            assumptions=(),
            obvious_solution="Unavailable: task framing failed.",
        )

    def _seed_and_evaluate(
        self,
        framed_task: FramedTask,
        config: RunConfig,
        budget: BudgetController,
        errors: list[RunError],
        providers: RunProviders,
    ) -> tuple[list[IdeaGenome], str | None]:
        try:
            seed_quote = validate_quote(self._seeder.quote_seed(framed_task, config))
        except Exception:
            _error(
                errors,
                stage="seeding",
                provider=providers.seeder.name,
                category="quote_error",
                message="provider quote failed validation",
                cost_incurred=False,
            )
            return [], "provider_error"
        try:
            evaluation_quote = validate_quote(
                self._evaluator.quote_evaluation(framed_task)
            )
        except Exception:
            _error(
                errors,
                stage="evaluation",
                provider=providers.evaluator.name,
                category="quote_error",
                message="provider quote failed validation",
                cost_incurred=False,
            )
            return [], "provider_error"

        try:
            reservation = budget.reserve(
                seed_quote.max_cost_usd
                + evaluation_quote.max_cost_usd * config.seed_count,
                required_calls=seed_quote.calls
                + evaluation_quote.calls * config.seed_count,
                preserve_finalization=True,
            )
        except BudgetExceeded:
            _error(
                errors,
                stage="seeding",
                provider=providers.seeder.name,
                category="budget_error",
                message="insufficient budget for seed batch",
                cost_incurred=False,
            )
            return [], "budget_exhausted"

        with reservation:
            try:
                seeded = validate_metered_envelope(
                    self._seeder.seed(framed_task, config)
                )
            except ValidationError:
                _error(
                    errors,
                    stage="seeding",
                    provider=providers.seeder.name,
                    category="validation_error",
                    message="provider returned invalid metered response",
                    cost_incurred=False,
                )
                return [], "provider_error"
            except Exception:
                _error(
                    errors,
                    stage="seeding",
                    provider=providers.seeder.name,
                    category="provider_error",
                    message="provider operation failed",
                    cost_incurred=False,
                )
                return [], "provider_error"

            if not self._charge_response(
                seeded,
                seed_quote,
                reservation,
                budget,
                stage="seeding",
                expected_provider=providers.seeder.name,
                errors=errors,
            ):
                return [], "provider_error"

            try:
                seeds = validate_seed_payload(seeded, config=config)
            except (ValidationError, ValueError) as error:
                category = (
                    "cardinality_error"
                    if "cardinality" in str(error).lower()
                    else "validation_error"
                )
                _error(
                    errors,
                    stage="seeding",
                    provider=providers.seeder.name,
                    category=category,
                    message="provider returned invalid seed candidates",
                    cost_incurred=True,
                )
                return [], "provider_error"

            seed_cost = Decimal(str(seeded.cost_usd)) / Decimal(len(seeds))
            seed_latency = Decimal(str(seeded.latency_ms)) / Decimal(len(seeds))
            evaluated: list[IdeaGenome] = []
            for index, candidate in enumerate(seeds):
                attributed = _validated_candidate(
                    candidate,
                    branch_cost=seed_cost,
                    branch_latency=seed_latency,
                )
                result = self._evaluate(
                    attributed,
                    framed_task,
                    evaluation_quote,
                    reservation,
                    budget,
                    errors,
                    providers,
                )
                if result is None:
                    evaluated.append(attributed)
                    evaluated.extend(
                        _validated_candidate(
                            remaining,
                            branch_cost=seed_cost,
                            branch_latency=seed_latency,
                        )
                        for remaining in seeds[index + 1 :]
                    )
                    return evaluated, "provider_error"
                evaluated.append(result)
            return evaluated, None

    def _transform_and_evaluate(
        self,
        request: TransformationRequest,
        parents: tuple[IdeaGenome, ...],
        framed_task: FramedTask,
        budget: BudgetController,
        candidate_ids: set[UUID],
        errors: list[RunError],
        providers: RunProviders,
    ) -> tuple[IdeaGenome | None, str | None]:
        try:
            transform_quote = validate_quote(
                self._transformer.quote_transform(request, parents)
            )
        except Exception:
            _error(
                errors,
                stage="transformation",
                provider=providers.transformer.name,
                category="quote_error",
                message="provider quote failed validation",
                cost_incurred=False,
            )
            return None, "provider_error"
        try:
            evaluation_quote = validate_quote(
                self._evaluator.quote_evaluation(framed_task)
            )
        except Exception:
            _error(
                errors,
                stage="evaluation",
                provider=providers.evaluator.name,
                category="quote_error",
                message="provider quote failed validation",
                cost_incurred=False,
            )
            return None, "provider_error"

        try:
            reservation = budget.reserve(
                transform_quote.max_cost_usd + evaluation_quote.max_cost_usd,
                required_calls=transform_quote.calls + evaluation_quote.calls,
                preserve_finalization=True,
            )
        except BudgetExceeded:
            _error(
                errors,
                stage="transformation",
                provider=providers.transformer.name,
                category="budget_error",
                message="insufficient budget for transformation",
                cost_incurred=False,
            )
            return None, "budget_exhausted"

        with reservation:
            try:
                transformed = validate_metered_envelope(
                    self._transformer.transform(request, parents)
                )
            except ValidationError:
                _error(
                    errors,
                    stage="transformation",
                    provider=providers.transformer.name,
                    category="validation_error",
                    message="provider returned invalid metered response",
                    cost_incurred=False,
                )
                return None, "provider_error"
            except Exception:
                _error(
                    errors,
                    stage="transformation",
                    provider=providers.transformer.name,
                    category="provider_error",
                    message="provider operation failed",
                    cost_incurred=False,
                )
                return None, "provider_error"

            if not self._charge_response(
                transformed,
                transform_quote,
                reservation,
                budget,
                stage="transformation",
                expected_provider=providers.transformer.name,
                errors=errors,
            ):
                return None, "provider_error"

            try:
                candidate = validate_transform_payload(
                    transformed,
                    request=request,
                    parents=parents,
                    candidate_ids=candidate_ids,
                )
            except (ValidationError, ValueError):
                _error(
                    errors,
                    stage="transformation",
                    provider=providers.transformer.name,
                    category="validation_error",
                    message="provider returned invalid transform candidate",
                    cost_incurred=True,
                )
                return None, "provider_error"

            parent_cost = sum(
                (Decimal(str(parent.branch_cost_usd)) for parent in parents),
                start=Decimal("0"),
            )
            parent_latency = sum(
                (Decimal(str(parent.branch_latency_ms)) for parent in parents),
                start=Decimal("0"),
            )
            attributed = _validated_candidate(
                candidate,
                branch_cost=parent_cost + Decimal(str(transformed.cost_usd)),
                branch_latency=parent_latency + Decimal(str(transformed.latency_ms)),
            )
            evaluated = self._evaluate(
                attributed,
                framed_task,
                evaluation_quote,
                reservation,
                budget,
                errors,
                providers,
            )
            if evaluated is None:
                return None, "provider_error"
            return evaluated, None

    def _evaluate(
        self,
        candidate: IdeaGenome,
        framed_task: FramedTask,
        quote: OperationQuote,
        reservation: BudgetReservation,
        budget: BudgetController,
        errors: list[RunError],
        providers: RunProviders,
    ) -> IdeaGenome | None:
        try:
            response = validate_metered_envelope(
                self._evaluator.evaluate(candidate, framed_task)
            )
        except ValidationError:
            _error(
                errors,
                stage="evaluation",
                provider=providers.evaluator.name,
                category="validation_error",
                message="provider returned invalid metered response",
                cost_incurred=False,
            )
            return None
        except Exception:
            _error(
                errors,
                stage="evaluation",
                provider=providers.evaluator.name,
                category="provider_error",
                message="provider operation failed",
                cost_incurred=False,
            )
            return None

        if not self._charge_response(
            response,
            quote,
            reservation,
            budget,
            stage="evaluation",
            expected_provider=providers.evaluator.name,
            errors=errors,
        ):
            return None
        try:
            scores = validate_evaluation_payload(response)
        except ValidationError:
            _error(
                errors,
                stage="evaluation",
                provider=providers.evaluator.name,
                category="validation_error",
                message="provider returned invalid evaluation scores",
                cost_incurred=True,
            )
            return None

        return _validated_candidate(
            candidate,
            scores=scores,
            branch_cost=(
                Decimal(str(candidate.branch_cost_usd))
                + Decimal(str(response.cost_usd))
            ),
            branch_latency=(
                Decimal(str(candidate.branch_latency_ms))
                + Decimal(str(response.latency_ms))
            ),
        )

    @staticmethod
    def _charge_response(
        response: MeteredResponse[object],
        quote: OperationQuote,
        reservation: BudgetReservation,
        budget: BudgetController,
        *,
        stage: str,
        expected_provider: str,
        errors: list[RunError],
    ) -> bool:
        exceeds_quote = _exceeds_quote(response, quote)
        if exceeds_quote:
            try:
                budget.record_audited_overage(
                    reservation,
                    stage,
                    expected_provider,
                    response.cost_usd,
                    response.latency_ms,
                    quoted_cost_usd=quote.max_cost_usd,
                    model=response.model,
                    usage=response.usage,
                    pricing_version=response.pricing_version,
                    cost_is_estimated=response.cost_is_estimated,
                    request_id=response.request_id,
                    operation_trace=response.operation_trace,
                    calls=response.calls,
                )
            except Exception:
                _error(
                    errors,
                    stage=stage,
                    provider=expected_provider,
                    category="accounting_error",
                    message="failed to record provider overage",
                    cost_incurred=True,
                )
                return False
        else:
            try:
                reservation.charge(
                    stage,
                    expected_provider,
                    response.cost_usd,
                    response.latency_ms,
                    model=response.model,
                    usage=response.usage,
                    pricing_version=response.pricing_version,
                    cost_is_estimated=response.cost_is_estimated,
                    request_id=response.request_id,
                    operation_trace=response.operation_trace,
                    calls=response.calls,
                )
            except BudgetExceeded:
                _error(
                    errors,
                    stage=stage,
                    provider=expected_provider,
                    category="accounting_error",
                    message="provider cost could not be charged",
                    cost_incurred=True,
                )
                return False
        if response.provider != expected_provider:
            _error(
                errors,
                stage=stage,
                provider=expected_provider,
                category="provider_error",
                message="provider identity mismatch",
                cost_incurred=True,
            )
            return False
        if exceeds_quote:
            _error(
                errors,
                stage=stage,
                provider=expected_provider,
                category="overage_error",
                message="provider cost exceeded quote",
                cost_incurred=True,
            )
            return False
        return True

    def _result(
        self,
        framed_task: FramedTask,
        candidates: tuple[IdeaGenome, ...],
        budget: BudgetController,
        config: RunConfig,
        providers: RunProviders,
        errors: list[RunError],
        stopped_reason: str,
    ) -> RunResult:
        finalist_pool = tuple(
            candidate for candidate in candidates if candidate.scores is not None
        )
        if finalist_pool:
            finalists = self._population.select(
                finalist_pool,
                finalist_count=min(config.finalist_count, len(finalist_pool)),
            )
        else:
            finalists = candidates[: config.finalist_count]
        return RunResult(
            config=config,
            providers=providers,
            operator_schedule=tuple(operator.value for operator in OPERATOR_SCHEDULE),
            framed_task=framed_task,
            finalists=finalists,
            all_candidates=candidates,
            spend_records=budget.records,
            errors=tuple(errors),
            stopped_reason=stopped_reason,
        )
