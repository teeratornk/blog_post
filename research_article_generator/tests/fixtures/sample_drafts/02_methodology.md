# Methodology

## Problem Formulation

Consider a general PDE of the form:

$$\mathcal{L}[u](\mathbf{x}) = f(\mathbf{x}), \quad \mathbf{x} \in \Omega$$

subject to boundary conditions:

$$\mathcal{B}[u](\mathbf{x}) = g(\mathbf{x}), \quad \mathbf{x} \in \partial\Omega$$

where $\mathcal{L}$ is a differential operator, $\Omega \subset \mathbb{R}^d$
is the computational domain, and $\partial\Omega$ is its boundary.

## Neural Network Approximation

We approximate the solution $u(\mathbf{x})$ using a deep neural network
$u_\theta(\mathbf{x})$ with parameters $\theta$. The loss function is:

$$\mathcal{J}(\theta) = \lambda_r \mathcal{J}_r(\theta) + \lambda_b \mathcal{J}_b(\theta)$$

where $\mathcal{J}_r$ is the residual loss and $\mathcal{J}_b$ is the boundary
loss \cite{raissi2019physics}.

![Training convergence](figures/convergence.png){#fig:convergence}

As shown in Figure @fig:convergence, the training converges rapidly after
approximately 1000 epochs.
