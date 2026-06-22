# Creativity Layer Research Prototype Design

## 1. Purpose

The Creativity Layer is a domain-independent inference-time system for improving the creative work of AI agents. It targets developers building agents, but the first version is a research prototype rather than a production SDK.

The prototype will test this falsifiable claim:

> Under realistic compute constraints, evolutionary creative search produces outputs that requesting users and independent reviewers judge as simultaneously more original and useful than strong prompting of the same base models.

The system does not claim to produce ideas without influence or to prove absolute originality. It aims to produce ideas that are unexpectedly different, valuable for the current user and task, and transformed enough to have a coherent identity rather than resembling their inspirations.

## 2. Product Principles

Creativity is treated as contextual and multi-dimensional:

- **Originality:** The idea differs structurally from obvious answers, peer candidates, model expectations, and discoverable prior art.
- **Usefulness:** The idea creates meaningful value for the task.
- **User fit:** The idea accounts for the requesting user's goals, preferences, and risk tolerance.
- **Coherence:** The idea's components form a defensible whole rather than a random collection of unusual elements.
- **Productive surprise:** The result may challenge the user's existing preferences when doing so creates value.

These dimensions remain separate during evaluation. Novelty cannot compensate for uselessness, and familiarity cannot substitute for quality.

## 3. Scope

### Phase 1: Core proof

Phase 1 includes:

- Evolutionary creative search
- Structured idea genomes
- Independent and inspiration-driven branches
- Adaptive compute and cost controls
- Search-based inspiration and prior-art checks
- Eight benchmark families
- Blind evaluation by requesting users and independent reviewers
- Reproducible experiment traces

Phase 1 excludes:

- Persistent creative identity
- Production hosting
- Multi-user account infrastructure
- Broad agent-framework integrations
- Autonomous identity evolution
- Claims of absolute originality

### Phase 2: Persistent creative identity

After the core process is validated, Phase 2 adds:

- Persistent agent identity
- A user-controlled identity constitution
- Feedback-driven identity evolution
- Optional shared creative lineages
- Dissent mechanisms to prevent groupthink
- Identity drift, user-fit, and long-term originality experiments

### Phase 3: Developer product

After research validation, Phase 3 adds:

- A model-agnostic API and SDK
- Agent-framework integrations
- Configurable domain adapters
- A trace and evaluation dashboard
- Privacy, access, and multi-user controls

## 4. Core Creative Process

The prototype runs a population-based creative search.

1. **Frame:** Model the task, user, goals, constraints, assumptions, and obvious-solution baseline.
2. **Seed:** Generate candidates from independent branches. At least one branch remains isolated from external search.
3. **Abstract:** Convert each candidate from prose into a structured representation of its underlying mechanism.
4. **Transform:** Apply structural mutations, including inversion, analogy, subtraction, contradiction, cross-domain transfer, and combination.
5. **Search:** Gather inspiration for selected branches and convert sources into abstract principles before creative reuse.
6. **Simulate:** Examine consequences, utility, feasibility, uncertainties, and failure modes.
7. **Check novelty:** Compare candidates with each other, expected answers, and searchable prior art.
8. **Select and deepen:** Allocate additional compute to candidates on the originality-usefulness frontier while retaining a protected wildcard.
9. **Stop adaptively:** Continue only while additional generations improve the frontier within the run's limits.
10. **Present:** Show ideas before their justifications, collect initial reactions where possible, and then explain task fit, user fit, provenance, and risks.

Evaluators must not eliminate a candidate solely because it is unfamiliar. Originality, usefulness, coherence, feasibility, and user fit are scored independently before any selection decision.

## 5. User-Task Model

The layer builds a temporary user-task model for each run. It combines:

- Explicit task goals and constraints
- Relevant conversation context
- Available user preferences and prior feedback
- Risk, feasibility, and time expectations
- Uncertainty about preferences that materially affect the result

The layer infers a provisional model first. It asks questions only when unresolved uncertainty could materially change the creative direction. It may also use contrasting taste probes and learn from what the user accepts, rejects, edits, or describes as obvious.

Personalization must not reduce the system to a recommendation engine. The process reserves capacity for productive surprise: ideas the user did not request directly but may value after understanding them.

## 6. Idea Genome

Each candidate is stored as an idea genome rather than prose alone.

An idea genome contains:

- Candidate identifier and generation
- Core mechanism
- Problem framing
- Assumptions challenged
- Intended user and task value
- Distinguishing structural features
- Inspiration principles and source provenance
- Predicted first- and second-order consequences
- Feasibility assumptions
- Uncertainties, weaknesses, and failure modes
- Parent candidates
- Transformations applied
- Evaluation history
- Cost and latency attributable to the branch

The genome permits transformations, comparisons, ancestry tracking, and evaluation without depending on a candidate's presentation style.

## 7. Transformation Engine

The initial transformation operators are:

- **Invert:** Reverse a foundational assumption.
- **Transfer:** Import an abstract mechanism from a distant domain.
- **Combine:** Merge compatible mechanisms rather than descriptions.
- **Exaggerate:** Push one property to an extreme and inspect the consequences.
- **Subtract:** Remove a supposedly essential component.
- **Reframe:** Redefine the underlying problem.
- **Contradict:** Attempt to satisfy apparently incompatible goals.
- **Personalize:** Reshape the concept around the current user and task.
- **Distill:** Remove borrowed surface characteristics while preserving useful principles.

Every generation includes:

- Independently generated candidates
- Inspiration-derived candidates
- Crossbred candidates
- At least one wildcard protected from early elimination

Predefined transformations may become repetitive. The system may propose new operators during a run. A proposed operator is retained only when its descendants add useful structural novelty across repeated experiments.

## 8. Inspiration, Provenance, and Anti-Copying

Search has two distinct purposes.

### Inspiration search

Inspiration search explores relevant and distant domains. It extracts mechanisms, emotional effects, tensions, constraints, relationships, and principles rather than surface features.

Most creative stages receive these abstractions, not raw source material. A later verifier retains access to the original sources for accurate comparison.

### Prior-art search

Prior-art search examines finalists for meaningful similarity to discoverable existing work. It estimates novelty but does not prove originality.

### Safeguards

- At least one ideation branch never sees search results.
- Search is selective rather than mandatory for every branch.
- Sources are abstracted before most transformations.
- Finalists are compared with sources at surface and structural levels.
- Excessive similarity triggers another transformation, rejection, or transparent attribution.
- Every candidate retains sources, inherited principles, mutations, and ancestry.
- Outputs are labeled as independent, inspired, synthesized, or adapted.

## 9. Domain-General Core and Adapters

The shared engine handles framing, genomes, search, transformations, novelty analysis, provenance, compute allocation, and experiment tracing.

Thin domain adapters define output contracts, validation methods, and domain-specific quality criteria. They must not contain premade creative solutions or templates.

Phase 1 benchmarks eight task families:

1. Product and business ideas
2. Fiction, storytelling, and poetry
3. UI, visual, and interaction design
4. Technical invention and engineering
5. Strategy and planning
6. Scientific hypotheses and experiments
7. Marketing, branding, and communication
8. Creative problem-solving under unusual constraints

Examples of adapter-specific evaluation include:

- Ideation: differentiation, utility, and feasibility
- Writing: voice, emotional effect, and narrative coherence
- UI and design: interaction quality, usability, and visual identity
- Strategy: leverage, defensibility, and second-order effects
- Technical invention: correctness, feasibility, and mechanism quality
- Scientific work: plausibility, testability, and information value

The architecture may accept other text-representable creative tasks, but evidence-backed performance claims apply only to tested domains.

## 10. System Components

### Task Framer

Creates the user-task model, explicit constraints, assumptions, evaluation dimensions, and obvious-solution baseline.

### Population Manager

Maintains candidate genomes, ancestry, generation boundaries, diversity, and wildcard protection.

### Transformation Engine

Chooses and applies structural transformation operators and evaluates proposed new operators.

### Inspiration Engine

Runs selective searches, retrieves source material, extracts abstractions, and preserves source provenance.

### Novelty Engine

Compares candidates against the population, obvious baselines, model expectations, and searchable prior art.

### Simulation and Domain Evaluators

Test predicted consequences and assess domain-specific usefulness, coherence, feasibility, and quality.

### Budget Controller

Allocates model calls, model tiers, search operations, elapsed time, and dollar cost.

### Experiment Harness

Runs baselines, randomizes outputs, collects blind judgments, and computes comparative results.

### Trace Store

Preserves configurations, prompts, structured outputs, model and provider metadata, sources, genomes, scores, ancestry, costs, and errors.

Each module exposes structured inputs and outputs so models, providers, scoring methods, and domain adapters can be replaced independently.

## 11. Data Flow

The top-level data flow is:

`Task → framing → seed population → transformation/search/simulation cycles → originality-usefulness frontier → finalist refinement → presentation → blind evaluation`

During each cycle:

1. The Population Manager selects parents and protected candidates.
2. The Budget Controller assigns an allowable operation and model tier.
3. The Transformation or Inspiration Engine produces descendants.
4. Structured-output validation rejects or repairs malformed genomes.
5. The Novelty Engine removes near-duplicates and records novelty dimensions.
6. Domain Evaluators assess value without seeing persuasive justification where practical.
7. The Population Manager updates the frontier and ancestry.
8. The stopping controller measures marginal improvement.

## 12. Adaptive Cost Control

Each run accepts:

- Maximum dollar cost
- Maximum duration
- Maximum model calls
- Search permissions
- Required output count
- Allowed providers and model tiers

The controller:

1. Reserves budget for framing, final evaluation, and one wildcard.
2. Uses cheaper models for broad seed generation and mutations.
3. Removes semantic and structural duplicates before expensive evaluation.
4. Allocates more compute to promising and unusually different branches.
5. Searches only when inspiration or originality verification adds expected value.
6. Uses stronger models for difficult simulation, evaluation, and final refinement.
7. Stops when recent operations no longer improve the originality-usefulness frontier enough to justify their cost.

The research harness compares multiple budgets rather than assuming a default price. Initial experiment levels are approximately $0.10, $0.50, $1.00, and up to $5.00 per task, adjusted for provider pricing at experiment time.

The harness also compares cheap-model seeding with strong-model seeding. This reveals whether early cost savings irreversibly constrain later search quality.

If a run exhausts its budget, it returns the strongest current candidates together with confidence, provenance, unresolved risks, and skipped stages.

## 13. Evaluation Design

Each benchmark task compares:

- A base model with a normal prompt
- The same base model with a strong prompt
- The same base model using the Creativity Layer
- The Creativity Layer at multiple compute budgets

Where practical, conditions share equivalent task context and output limits. Outputs are anonymized and randomized.

### Requesting-user evaluation

The requesting user scores:

- Personal value
- Task fit
- Surprise
- Desire to use, develop, or adopt the idea

The idea is shown before its justification when practical. The system can record an initial reaction, reveal the explanation, and then allow a revised judgment.

### Independent evaluation

Independent reviewers score:

- Originality
- Usefulness
- Coherence
- Domain quality
- Whether novelty is structural or cosmetic

Reviewers should have relevant domain knowledge when the task requires it.

### Automated and operational measures

The system also records:

- Similarity to discoverable prior art
- Diversity between candidates
- Repeated patterns across unrelated tasks
- Similarity to inspiration sources
- Cost and latency
- Improvement per additional call or dollar
- Reviewer disagreement
- Failure and retry rates

### Primary success metric

The primary metric is the proportion of Creativity Layer outputs that beat the strongest baseline on both originality and usefulness. Average scores are secondary because averaging could allow useless novelty to compensate for poor value.

Results are reported by domain, model, compute budget, and evaluator group. The prototype succeeds only if gains are repeatable across multiple task families rather than driven by one domain.

## 14. Reliability and Testing

### Unit tests

Unit tests cover:

- Genome schema validation
- Transformation correctness
- Parent and source provenance
- Budget accounting
- Deduplication
- Frontier updates
- Wildcard retention
- Stopping rules
- Structured model-output parsing and repair

### Pipeline tests

Deterministic mocked runs cover:

- Search failures
- Model timeouts
- Malformed responses
- Exhausted budgets
- Duplicate populations
- Empty search results
- Judge disagreement
- Partial provider outages
- Interrupted and resumed runs

Retries are bounded and charged to the run budget. When a dependency remains unavailable, the run degrades explicitly and records the skipped capability.

### Research validity tests

Research tests examine:

- Judge preference for verbosity or persuasive presentation
- Novelty scoring that rewards randomness
- Search anchoring
- Source imitation
- Premature removal of unconventional candidates
- Repeated structures across unrelated tasks
- Domain adapters supplying the creative content
- Personalization reducing productive surprise
- Strong-model judges preferring their own stylistic patterns
- Cost increases that fail to improve human-rated creativity

Where provider behavior permits, a run is reproducible from its configuration, model versions, random seed, prompts, retrieved sources, structured outputs, and trace. Exact token-level reproduction is not guaranteed for nondeterministic external APIs.

## 15. Persistent Creative Identity

Persistent identity is intentionally excluded from the Phase 1 causal experiment.

Phase 2 introduces three identity layers:

- **Agent identity:** Evolving values, curiosities, tendencies, contradictions, memories, and anti-habits unique to an agent.
- **Shared creative lineage:** Optional principles, abstractions, and creative history shared by agents working in related spaces.
- **Task identity:** A temporary perspective adopted for a specific assignment.

The user controls constitution-level values, boundaries, and desired qualities. Learned identity evolves from accepted, rejected, edited, and unexpectedly successful work. Learned changes remain inspectable and reversible.

The layer may detect related work and suggest a shared lineage, but it never merges identities automatically. Suggestions identify what would be shared and warn about groupthink. Agents in a lineage retain individual identities and receive explicit dissent or exploration objectives.

Phase 2 experiments test whether identity improves user fit over time without decreasing originality, narrowing the search space, or turning into a fixed style preset.

## 16. Risks and Mitigations

### Mechanical transformations

Risk: The process repeatedly applies named operators without producing deep conceptual change.

Mitigation: Compare structural genomes, measure operator yield, retire low-yield operators, and permit experimentally validated operators invented during runs.

### Judge convergence

Risk: Model judges reward familiar, polished answers and reject unconventional ideas.

Mitigation: Separate scoring dimensions, use blind human evaluation, retain wildcards, and audit judge behavior.

### Inspiration anchoring

Risk: Search causes candidates to imitate existing work.

Mitigation: Preserve a search-isolated branch, abstract sources, delay raw-source comparison until verification, and measure source similarity.

### Randomness mistaken for originality

Risk: Unusual but incoherent ideas score as novel.

Mitigation: Require simultaneous gains in usefulness and originality and maintain coherence as an independent threshold.

### High cost without gain

Risk: Multiple calls produce near-duplicates or elaborate weak ideas.

Mitigation: Deduplicate early, allocate compute adaptively, measure marginal improvement, and benchmark creativity-efficiency curves.

### Domain overfitting

Risk: Adapters or prompts make the system appear general while encoding domain solutions.

Mitigation: Keep adapters evaluative, test transfer to held-out tasks, inspect adapter content, and report results separately by domain.

### Identity-driven stagnation

Risk: Persistent identity becomes a style preset or shared lineages create groupthink.

Mitigation: Validate identity only after Phase 1, preserve anti-habits and dissent, monitor repetition, and support inspection and rollback.

## 17. Phase 1 Deliverables

Phase 1 is complete when the repository contains:

- A runnable local research pipeline
- Replaceable model and search provider interfaces
- The structured idea-genome schema
- Population, transformation, novelty, simulation, and budget modules
- At least one adapter for each benchmark family
- Baseline and blinded experiment tooling
- Reproducible trace storage
- Automated unit and pipeline tests
- A benchmark task set and reviewer rubric
- A report comparing conditions, domains, and compute budgets

The Phase 1 result may disprove or narrow the central claim. Negative results are valid: the objective is to determine whether the process creates measurable gains beyond strong prompting, not to preserve the premise at any cost.
