"""class for representing the state space of a model, and operations on it"""

import logging
import os
import subprocess
import sys
import numpy as np
import netCDF4 as nc

class ModelState:
    """class for representing the state space of a model"""

    def __init__(self, tracer_module_names, vals_fname=None):
        self._tracer_module_names = tracer_module_names
        self._tracer_module_cnt = len(tracer_module_names)
        if not vals_fname is None:
            self._tracer_modules = np.empty(shape=(self._tracer_module_cnt,), dtype=np.object)
            for ind in range(self._tracer_module_cnt):
                self._tracer_modules[ind] = TracerModule(tracer_module_names[ind],
                                                         vals_fname=vals_fname)

    def dump(self, vals_fname):
        """dump ModelState object to a file"""
        with nc.Dataset(vals_fname, mode='w') as fptr:
            for action in ['define', 'write']:
                for ind in range(len(self._tracer_modules)):
                    self._tracer_modules[ind].dump(fptr, action)
        return self

    def log(self, msg):
        """write info of the instance to the log"""
        logger = logging.getLogger(__name__)
        val = self.norm()
        for ind in range(self._tracer_module_cnt):
            logger.info('%s,%s,%e', msg, self._tracer_module_names[ind], val[ind])

    # give ModelState operators higher priority than those of numpy
    __array_priority__ = 100

    def __neg__(self):
        """
        unary negation operator
        called to evaluate res = -self
        """
        res = ModelState(self._tracer_module_names)
        res._tracer_modules = -self._tracer_modules # pylint: disable=W0212
        return res

    def __add__(self, other):
        """
        addition operator
        called to evaluate res = self + other
        """
        res = ModelState(self._tracer_module_names)
        if isinstance(other, float):
            res._tracer_modules = self._tracer_modules + other # pylint: disable=W0212
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            res._tracer_modules = self._tracer_modules + other # pylint: disable=W0212
        elif isinstance(other, ModelState):
            res._tracer_modules = self._tracer_modules + other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __radd__(self, other):
        """
        reversed addition operator
        called to evaluate res = other + self
        """
        return self + other

    def __iadd__(self, other):
        """
        inplace addition operator
        called to evaluate self += other
        """
        if isinstance(other, float):
            self._tracer_modules += other
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            self._tracer_modules += other
        elif isinstance(other, ModelState):
            self._tracer_modules += other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def __sub__(self, other):
        """
        subtraction operator
        called to evaluate res = self - other
        """
        res = ModelState(self._tracer_module_names)
        if isinstance(other, float):
            res._tracer_modules = self._tracer_modules - other # pylint: disable=W0212
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            res._tracer_modules = self._tracer_modules - other # pylint: disable=W0212
        elif isinstance(other, ModelState):
            res._tracer_modules = self._tracer_modules - other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __isub__(self, other):
        """
        inplace subtraction operator
        called to evaluate self -= other
        """
        if isinstance(other, float):
            self._tracer_modules -= other
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            self._tracer_modules -= other
        elif isinstance(other, ModelState):
            self._tracer_modules -= other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def __mul__(self, other):
        """
        multiplication operator
        called to evaluate res = self * other
        """
        res = ModelState(self._tracer_module_names)
        if isinstance(other, float):
            res._tracer_modules = self._tracer_modules * other # pylint: disable=W0212
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            res._tracer_modules = self._tracer_modules * other # pylint: disable=W0212
        elif isinstance(other, ModelState):
            res._tracer_modules = self._tracer_modules * other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __rmul__(self, other):
        """
        reversed multiplication operator
        called to evaluate res = other * self
        """
        return self * other

    def __imul__(self, other):
        """
        inplace multiplication operator
        called to evaluate self *= other
        """
        if isinstance(other, float):
            self._tracer_modules *= other
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            self._tracer_modules *= other
        elif isinstance(other, ModelState):
            self._tracer_modules *= other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def __truediv__(self, other):
        """
        division operator
        called to evaluate res = self / other
        """
        res = ModelState(self._tracer_module_names)
        if isinstance(other, float):
            res._tracer_modules = (1.0 / other) * self._tracer_modules # pylint: disable=W0212
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            res._tracer_modules = (1.0 / other) * self._tracer_modules # pylint: disable=W0212
        elif isinstance(other, ModelState):
            res._tracer_modules = self._tracer_modules / other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __rtruediv__(self, other):
        """
        reversed division operator
        called to evaluate res = other / self
        """
        res = ModelState(self._tracer_module_names)
        if isinstance(other, float):
            res._tracer_modules = other / self._tracer_modules # pylint: disable=W0212
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            res._tracer_modules = other / self._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __itruediv__(self, other):
        """
        inplace division operator
        called to evaluate self /= other
        """
        if isinstance(other, float):
            self._tracer_modules *= (1.0 / other)
        elif isinstance(other, np.ndarray) and other.shape == (self._tracer_module_cnt,):
            self._tracer_modules *= (1.0 / other)
        elif isinstance(other, ModelState):
            self._tracer_modules /= other._tracer_modules # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def dot(self, other):
        """compute dot product of self with other"""
        res = np.empty(shape=(self._tracer_module_cnt,))
        for ind in range(self._tracer_module_cnt):
            res[ind] = self._tracer_modules[ind].dot(other._tracer_modules[ind]) # pylint: disable=W0212
        return res

    def norm(self):
        """compute l2 norm of self"""
        return np.sqrt(self.dot(self))

    def converged(self):
        """is residual small"""
        return all(self.norm() < 1.0e-10)

    def mod_gram_schmidt(self, cnt, fname_fcn, quantity):
        """
        inplace modified Gram-Schmidt projection
        return projection coefficients
        """
        h_val = np.empty(shape=(self._tracer_module_cnt, cnt))
        for i_val in range(0, cnt):
            basis_i = ModelState(self._tracer_module_names, fname_fcn(quantity, i_val))
            h_val[:, i_val] = self.dot(basis_i)
            self -= h_val[:, i_val] * basis_i
        return h_val

    def run_ext_cmd(self, ext_cmd, res_fname, solver_state):
        """
        Run an external command (e.g., a shell script).
        The external command is expected to take 2 arguments: in_fname, res_fname
        in_fname is populated with the contents of self

        Skip running the command if currstep generated below has been logged in solver_state.
        """
        logger = logging.getLogger(__name__)
        logger.debug('entering, ext_cmd="%s", res_fname="%s"', ext_cmd, res_fname)

        currstep = 'calling %s for %s'%(ext_cmd, res_fname)
        solver_state.set_currstep(currstep)

        if solver_state.currstep_logged():
            logger.info('"%s" logged, skipping %s and returning result', currstep, ext_cmd)
            return ModelState(self._tracer_module_names, res_fname)

        logger.info('"%s" not logged, invoking %s and exiting', currstep, ext_cmd)

        ext_cmd_in_fname = os.path.join(solver_state.get_workdir(), 'ext_in.nc')
        self.dump(ext_cmd_in_fname)
        subprocess.Popen(['/bin/bash', ext_cmd, ext_cmd_in_fname, res_fname])

        logger.debug('flushing solver_state')
        solver_state.flush()

        logger.debug('calling exit')
        sys.exit()

    def comp_jacobian_fcn_state_prod(self, fcn, direction, solver_state):
        """
        compute the product of the Jacobian of fcn at self with the model state direction

        assumes direction is a unit vector
        """
        logger = logging.getLogger(__name__)
        logger.debug('entering')

        sigma = 1.0e-5 * self.norm()

        res_fname = os.path.join(solver_state.get_workdir(), 'fcn_res.nc')

        solver_state.set_currstep('comp_jacobian_fcn_state_prod_comp_fcn')
        # skip computation of peturbed state if corresponding run_ext_cmd has already been run
        if not solver_state.currstep_logged():
            (self + sigma * direction).run_ext_cmd('./comp_fcn.sh', res_fname, solver_state)

        # retrieve comp_fcn result from res_fname, and proceed with finite difference
        logger.debug('returning')
        return (ModelState(self._tracer_module_names, res_fname) - fcn) / sigma

def lin_comb(tracer_module_names, coeff, fname_fcn, quantity):
    """compute a linear combination of ModelState objects in files"""
    res = coeff[:, 0] * ModelState(tracer_module_names, fname_fcn(quantity, 0))
    for j_val in range(1, coeff.shape[-1]):
        res += coeff[:, j_val] * ModelState(tracer_module_names, fname_fcn(quantity, j_val))
    return res

class TracerModule:
    """class for representing the a collection of model tracers"""

    def __init__(self, name, dims=None, vals_fname=None):
        module_varnames = {'x':['x1', 'x2'], 'y':['y']}

        self._name = name
        try:
            self._varnames = module_varnames[name]
        except KeyError:
            raise KeyError('unknown TracerModule name=', name)
        if dims is None != vals_fname is None:
            raise ValueError('exactly one of dims and vals_fname must be passed')
        if not dims is None:
            self._dims = dims
        if not vals_fname is None:
            self._dims = {}
            with nc.Dataset(vals_fname, mode='r') as fptr:
                # get dims from first variable
                dimnames0 = fptr.variables[self._varnames[0]].dimensions
                for dimname in dimnames0:
                    self._dims[dimname] = fptr.dimensions[dimname].size
                # all tracers are stored in a single array
                # tracer index is the leading index
                self._vals = np.empty(shape=(len(self._varnames),) + tuple(self._dims.values()))
                # check that all vars have the same dimensions
                for varname in self._varnames:
                    if fptr.variables[varname].dimensions != dimnames0:
                        raise ValueError('not all vars have same dimensions',
                                         'TracerModule name=', name,
                                         'vals_fname=', vals_fname)
                # read values
                if len(self._dims) > 3:
                    raise ValueError('ndims too large (for implementation of dot)',
                                     'TracerModule name=', name,
                                     'fals_fname=', vals_fname,
                                     'ndims=', len(self._dims))
                for varind, varname in enumerate(self._varnames):
                    varid = fptr.variables[varname]
                    self._vals[varind, :] = varid[:]

    def dump(self, fptr, action):
        """perform an action (define or write) of dumping a TracerModule object to an open file"""
        if action == 'define':
            for dimname, dimlen in self._dims.items():
                try:
                    if fptr.dimensions[dimname].size != dimlen:
                        raise ValueError('dimname already exists and has wrong size',
                                         'TracerModule name=', self._name,
                                         'dimname=', dimname)
                except KeyError:
                    fptr.createDimension(dimname, dimlen)
            dimnames = tuple(self._dims.keys())
            for varname in self._varnames:
                fptr.createVariable(varname, 'f8', dimensions=dimnames)
        elif action == 'write':
            for varind, varname in enumerate(self._varnames):
                fptr.variables[varname][:] = self._vals[varind, :]
        else:
            raise ValueError('unknown action=', action)
        return self

    def __neg__(self):
        """
        unary negation operator
        called to evaluate res = -self
        """
        res = TracerModule(self._name, dims=self._dims)
        res._vals = -self._vals # pylint: disable=W0212
        return res

    def __add__(self, other):
        """
        addition operator
        called to evaluate res = self + other
        """
        res = TracerModule(self._name, dims=self._dims)
        if isinstance(other, float):
            res._vals = self._vals + other # pylint: disable=W0212
        elif isinstance(other, TracerModule):
            res._vals = self._vals + other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __iadd__(self, other):
        """
        inplace addition operator
        called to evaluate self += other
        """
        if isinstance(other, float):
            self._vals += other
        elif isinstance(other, TracerModule):
            self._vals += other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def __sub__(self, other):
        """
        subtraction operator
        called to evaluate res = self - other
        """
        res = TracerModule(self._name, dims=self._dims)
        if isinstance(other, float):
            res._vals = self._vals - other # pylint: disable=W0212
        elif isinstance(other, TracerModule):
            res._vals = self._vals - other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __isub__(self, other):
        """
        inplace subtraction operator
        called to evaluate self -= other
        """
        if isinstance(other, float):
            self._vals -= other
        elif isinstance(other, TracerModule):
            self._vals -= other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def __mul__(self, other):
        """
        multiplication operator
        called to evaluate res = self * other
        """
        res = TracerModule(self._name, dims=self._dims)
        if isinstance(other, float):
            res._vals = self._vals * other # pylint: disable=W0212
        elif isinstance(other, TracerModule):
            res._vals = self._vals * other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __rmul__(self, other):
        """
        reversed multiplication operator
        called to evaluate res = other * self
        """
        return self * other

    def __imul__(self, other):
        """
        inplace multiplication operator
        called to evaluate self *= other
        """
        if isinstance(other, float):
            self._vals *= other
        elif isinstance(other, TracerModule):
            self._vals *= other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def __truediv__(self, other):
        """
        division operator
        called to evaluate res = self / other
        """
        res = TracerModule(self._name, dims=self._dims)
        if isinstance(other, float):
            res._vals = (1.0 / other) * self._vals # pylint: disable=W0212
        elif isinstance(other, TracerModule):
            res._vals = self._vals / other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __rtruediv__(self, other):
        """
        reversed division operator
        called to evaluate res = other / self
        """
        res = TracerModule(self._name, dims=self._dims)
        if isinstance(other, float):
            res._vals = other / self._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return res

    def __itruediv__(self, other):
        """
        inplace division operator
        called to evaluate self /= other
        """
        if isinstance(other, float):
            self._vals *= (1.0 / other)
        elif isinstance(other, TracerModule):
            self._vals /= other._vals # pylint: disable=W0212
        else:
            return NotImplemented
        return self

    def dot(self, other):
        """compute dot product of self with other"""
        ndims = len(self._dims)
        if ndims == 1:
            return np.einsum('ij,ij', self._vals, other._vals) # pylint: disable=W0212
        if ndims == 2:
            return np.einsum('ijk,ijk', self._vals, other._vals) # pylint: disable=W0212
        return np.einsum('ijkl,ijkl', self._vals, other._vals) # pylint: disable=W0212
