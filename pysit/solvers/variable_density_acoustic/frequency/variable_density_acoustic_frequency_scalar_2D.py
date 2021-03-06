import scipy.sparse as spsp

from pysit.solvers.wavefield_vector import *
from variable_density_acoustic_frequency_scalar_base import *

from pysit.util import Bunch
from pysit.util import PositiveEvenIntegers
from pysit.util.derivatives import build_derivative_matrix, build_heterogenous_laplacian
from pysit.util.matrix_helpers import build_sigma, make_diag_mtx

from pysit.util.solvers import inherit_dict

__all__ = ['VariableDensityAcousticFrequencyScalar_2D']

__docformat__ = "restructuredtext en"


@inherit_dict('supports', '_local_support_spec')
class VariableDensityAcousticFrequencyScalar_2D(VariableDensityAcousticFrequencyScalarBase):

    _local_support_spec = {'spatial_discretization': 'finite-difference',
                           'spatial_dimension': 2,
                           'spatial_accuracy_order': PositiveEvenIntegers,
                           'boundary_conditions': ['pml', 'pml-sim', 'dirichlet'],
                           'precision': ['single', 'double']}

    def __init__(self,
                 mesh,
                 spatial_accuracy_order=4,
                 spatial_shifted_differences=True,
                 **kwargs):

        self.operator_components = Bunch()

        self.spatial_accuracy_order = spatial_accuracy_order

        self.spatial_shifted_differences = spatial_shifted_differences

        VariableDensityAcousticFrequencyScalarBase.__init__(self,
                                                            mesh,
                                                            spatial_accuracy_order=spatial_accuracy_order,
                                                            spatial_shifted_differences=spatial_shifted_differences,
                                                            **kwargs)

    def _rebuild_operators(self):

        dof = self.mesh.dof(include_bc=True)

        oc = self.operator_components

        built = oc.get('_numpy_components_built', False)

        # build the static components
        if not built:
            # build sigmax
            sx = build_sigma(self.mesh, self.mesh.x)
            oc.sigmax = make_diag_mtx(sx)

            # build sigmaz
            sz = build_sigma(self.mesh, self.mesh.z)
            oc.sigmaz = make_diag_mtx(sz)

            # build Dx
            oc.minus_Dx = build_derivative_matrix(self.mesh,
                                                  1,
                                                  self.spatial_accuracy_order,
                                                  dimension='x',
                                                  use_shifted_differences=self.spatial_shifted_differences)
            oc.minus_Dx.data *= -1

            # build Dz
            oc.minus_Dz = build_derivative_matrix(self.mesh,
                                                  1,
                                                  self.spatial_accuracy_order,
                                                  dimension='z',
                                                  use_shifted_differences=self.spatial_shifted_differences)
            oc.minus_Dz.data *= -1

            # build other useful things
            oc.I = spsp.eye(dof, dof)
            oc.empty = spsp.csr_matrix((dof, dof))

            # useful intermediates
            oc.sigma_xz  = make_diag_mtx(sx*sz)
            oc.sigma_xPz = oc.sigmax + oc.sigmaz

            oc.minus_sigma_zMx_Dx = make_diag_mtx((sz-sx))*oc.minus_Dx
            oc.minus_sigma_xMz_Dz = make_diag_mtx((sx-sz))*oc.minus_Dz

            oc._numpy_components_built = True

        kappa = self.model_parameters.kappa
        rho = self.model_parameters.rho
        oc.m1 = make_diag_mtx((kappa**-1).reshape(-1,))
        oc.m2 = make_diag_mtx((rho**-1).reshape(-1,))
        # build heterogenous laplacian
        sh = self.mesh.shape(include_bc=True,as_grid=True)
        deltas = [self.mesh.x.delta,self.mesh.z.delta]
        oc.L = build_heterogenous_laplacian(sh,rho**-1,deltas)

        # oc.L is a heterogenous laplacian operator. It computes div(m2 grad), where m2 = 1/rho. 
        # Currently the creation of oc.L is slow. This is because we have implemented a cenetered heterogenous laplacian.
        # To speed up computation, we could compute a div(m2 grad) operator that is not centered by simply multiplying
        # a divergence operator by oc.m2 by a gradient operator.

        self.K = spsp.bmat([[oc.m1*oc.sigma_xz-oc.L, oc.minus_Dx*oc.m2, oc.minus_Dz*oc.m2 ],
                            [oc.minus_sigma_zMx_Dx, oc.sigmax,   oc.empty    ],
                            [oc.minus_sigma_xMz_Dz, oc.empty,    oc.sigmaz   ]])

        self.C = spsp.bmat([[oc.m1*oc.sigma_xPz, oc.empty, oc.empty],
                            [oc.empty,          oc.I,     oc.empty],
                            [oc.empty,          oc.empty, oc.I    ]])

        self.M = spsp.bmat([[    oc.m1, oc.empty, oc.empty],
                            [oc.empty, oc.empty, oc.empty],
                            [oc.empty, oc.empty, oc.empty]])

    class WavefieldVector(WavefieldVectorBase):

        aux_names = ['Phix', 'Phiz']
