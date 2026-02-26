# Abstract

Physics-informed neural networks (PINNs) provide a mesh-free framework for solving partial differential equations (PDEs) by embedding governing equations into the training loss. However, standard PINNs can exhibit slow or unstable convergence on stiff problems and may require careful tuning of collocation points and loss weights. We propose an enhanced PINN architecture that improves convergence for stiff PDEs via adaptive collocation point selection and multi-scale loss balancing. We outline the governing boundary-value problem formulation and the composite PINN loss, and demonstrate performance on benchmark problems (e.g., Burgers equation) with improved training behavior.

<!-- TODO: Add 1–2 sentences stating the main quantitative gains (error, convergence speed, stability) and the key benchmarks used. -->
<!-- TODO: Add a closing sentence on broader impact/applicability (e.g., higher-dimensional PDEs, inverse problems, complex geometries). -->
