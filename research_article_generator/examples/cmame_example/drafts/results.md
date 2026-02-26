# Results

<!-- TODO: Briefly restate the experimental goal: evaluate the proposed enhanced PINN (adaptive collocation + multi-scale loss balancing) against a standard PINN baseline on benchmark PDEs. -->

## Experimental setup

### Benchmarks and PDEs

<!-- TODO: Specify benchmark problems used (at minimum Burgers equation as mentioned in Introduction/Methodology). -->
<!-- TODO: Provide PDE form, domain, boundary/initial conditions, and any parameter settings (e.g., viscosity for Burgers). -->

### Baselines and ablations

<!-- TODO: Define the baseline model (standard PINN per \citep{raissi2019physics}). -->
<!-- TODO: Define ablations: (i) +adaptive collocation only, (ii) +loss balancing only, (iii) full method. -->

### Implementation and training protocol

<!-- TODO: Network architecture (depth/width/activations), optimizer(s), learning-rate schedule, training iterations/epochs. -->
<!-- TODO: Collocation sampling strategy and update frequency for adaptive collocation. -->
<!-- TODO: Loss weights (\lambda_r, \lambda_b, \lambda_d) and the proposed balancing rule/schedule. -->
<!-- TODO: Hardware/runtime reporting (GPU/CPU), number of runs/seeds. -->

### Evaluation metrics

<!-- TODO: Report metrics: relative L2 error, max error, PDE residual statistics, boundary violation, and convergence speed (iterations/time to reach threshold). -->
<!-- TODO: Describe how reference/ground-truth solution is obtained (analytic, high-resolution numerical solver, or dataset). -->

## Main quantitative results

<!-- TODO: Summarize key numbers (error and/or speed improvements) for each benchmark in text. -->

<!-- TODO: Add a table comparing methods across benchmarks and metrics. -->

## Training convergence and stability

Figure @fig:convergence shows representative training convergence on the Burgers equation.

<!-- TODO: Interpret Fig. @fig:convergence: compare slope/plateau behavior, stability/oscillations, and time-to-accuracy vs baseline. -->
<!-- TODO: If applicable, describe variance across random seeds and sensitivity to hyperparameters. -->

## Effect of adaptive collocation

<!-- TODO: Provide results showing how adaptive collocation changes error/residual concentration (e.g., improved accuracy near shocks/steep gradients). -->
<!-- TODO: Optionally include a visualization of collocation point distribution over training and relate it to residual hotspots. -->

## Effect of multi-scale loss balancing

<!-- TODO: Provide results showing improved conditioning of optimization (e.g., more balanced gradient norms across loss terms, fewer failure runs). -->
<!-- TODO: If possible, include a plot of loss weights/terms over training. -->

## Additional benchmarks / generalization

<!-- TODO: Add results for additional PDEs beyond Burgers (e.g., Poisson, Helmholtz, diffusion-reaction) and/or higher-dimensional cases if available. -->
<!-- TODO: Discuss generalization to different parameter regimes (e.g., varying viscosity) and robustness to noise in data term \mathcal{J}_d if used. -->

## Summary of findings

<!-- TODO: Provide 3–5 bullet points summarizing the main empirical takeaways (best-performing configuration, typical error reduction, convergence speedup, robustness). -->
