# Discussion

## Summary of findings

<!-- TODO: Summarize the key methodological contributions: improved convergence for stiff PDEs, adaptive collocation, multi-scale loss balancing. -->
<!-- TODO: Summarize the main empirical outcomes on benchmarks (e.g., Burgers): accuracy, convergence curves, robustness to hyperparameters. Reference Fig. @fig:convergence where appropriate. -->

## Why the proposed modifications help

<!-- TODO: Provide intuition/mechanistic explanation for why adaptive collocation improves residual enforcement (e.g., focusing samples where residual is large/regions with sharp gradients). -->
<!-- TODO: Explain how multi-scale loss balancing addresses gradient magnitude mismatch between residual/boundary/data terms (tie back to the composite loss \mathcal{J}(\theta)). -->

## Comparison to prior work

<!-- TODO: Compare against baseline PINN (Raissi et al.) and any key variants (e.g., adaptive sampling, curriculum, annealing weights). Use \citet{} / \citep{} style citations. -->
<!-- TODO: Clarify what is novel relative to existing adaptive collocation and weighting strategies. -->

## Limitations

<!-- TODO: Discuss limitations: computational cost (AD, higher-order derivatives), sensitivity to architecture/optimizer, scalability with dimension, handling noisy data, boundary condition complexity. -->
<!-- TODO: Note any failure cases observed (if any) and when the method may not help. -->

## Practical guidance

<!-- TODO: Provide recommended default settings (collocation update frequency, weighting schedule, network size) and troubleshooting tips. -->

## Future work

<!-- TODO: Outline next steps: extension to time-dependent/multiphysics PDEs, irregular geometries, uncertainty quantification, inverse problems, adaptive refinement criteria, theoretical convergence guarantees. -->
