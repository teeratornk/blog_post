# Methodology

## Problem Statement

Consider a general boundary value problem:

$$\mathcal{L}[u](\mathbf{x}) = f(\mathbf{x}), \quad \mathbf{x} \in \Omega \subset \mathbb{R}^d$$

$$\mathcal{B}[u](\mathbf{x}) = g(\mathbf{x}), \quad \mathbf{x} \in \partial\Omega$$

where $\mathcal{L}$ is a (possibly nonlinear) differential operator and
$\mathcal{B}$ is a boundary operator.

## Physics-Informed Neural Networks

We approximate $u(\mathbf{x})$ by a neural network $u_\theta(\mathbf{x})$
parameterized by $\theta$. The composite loss function is:

$$\mathcal{J}(\theta) = \lambda_r \mathcal{J}_r + \lambda_b \mathcal{J}_b + \lambda_d \mathcal{J}_d$$

where:

$$\mathcal{J}_r = \frac{1}{N_r} \sum_{i=1}^{N_r} |\mathcal{L}[u_\theta](\mathbf{x}_r^i) - f(\mathbf{x}_r^i)|^2$$

is the PDE residual loss, and $\mathcal{J}_b$ and $\mathcal{J}_d$ are boundary
and data losses respectively \cite{raissi2019physics}.

![Training convergence for Burgers equation](figures/convergence.png){#fig:convergence}

Figure @fig:convergence shows the training convergence for the Burgers equation
benchmark.
