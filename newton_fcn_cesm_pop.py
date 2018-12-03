#!/usr/bin/env python
"""cesm pop hooks for Newton-Krylov solver"""

from __future__ import division

import argparse
import configparser
import glob
import logging
import os
import shutil
import stat
import subprocess
import sys

import numpy as np

from netCDF4 import Dataset

from model import TracerModuleStateBase, ModelState, ModelStaticVars
from model import get_tracer_module_def, get_modelinfo

def _parse_args():
    """parse command line arguments"""
    parser = argparse.ArgumentParser(description="cesm pop hooks for Newton-Krylov solver")
    parser.add_argument('cmd', choices=['comp_fcn', 'apply_precond_jacobian'],
                        help='command to run')
    parser.add_argument('--cfg_fname', help='name of configuration file',
                        default='newton_krylov_cesm_pop.cfg')
    parser.add_argument('--hist_fname', help='name of history file', default=None)
    parser.add_argument('--in_fname', help='name of file with input')
    parser.add_argument('--res_fname', help='name of file for result')
    return parser.parse_args()

def main(args):
    """cesm pop hooks for Newton-Krylov solver"""

    config = configparser.ConfigParser()
    config.read(args.cfg_fname)
    solverinfo = config['solverinfo']

    logging.basicConfig(stream=sys.stdout,
                        format='%(asctime)s:%(process)s:%(filename)s:%(funcName)s:%(message)s',
                        level=solverinfo['logging_level'])
    logger = logging.getLogger(__name__)

    logger.info('entering, cmd=%s', args.cmd)

    # store cfg_fname in modelinfo, to ease access to its values elsewhere
    config['modelinfo']['cfg_fname'] = args.cfg_fname

    ModelStaticVars(config['modelinfo'])

    if args.cmd == 'comp_fcn':
        raise NotImplementedError(
            '%s not implemented for command line execution in %s ' % (args.cmd, __file__))
    elif args.cmd == 'apply_precond_jacobian':
        raise NotImplementedError(
            '%s not implemented for command line execution in %s ' % (args.cmd, __file__))
    else:
        raise ValueError('unknown cmd=%s' % args.cmd)

################################################################################

class TracerModuleState(TracerModuleStateBase):
    """
    Derived class for representing a collection of model tracers.
    It implements _read_vals and dump.
    """

    def _read_vals(self, tracer_module_name, vals_fname):
        """return tracer values and dimension names and lengths, read from vals_fname)"""
        logger = logging.getLogger(__name__)
        logger.debug('entering')
        dims = {}
        suffix = '_CUR'
        with Dataset(vals_fname, mode='r') as fptr:
            fptr.set_auto_mask(False)
            # get dims from first variable
            dimnames0 = fptr.variables[self.tracer_names()[0]+suffix].dimensions
            for dimname in dimnames0:
                dims[dimname] = fptr.dimensions[dimname].size
            # all tracers are stored in a single array
            # tracer index is the leading index
            vals = np.empty(shape=(self.tracer_cnt(),) + tuple(dims.values()))
            # check that all vars have the same dimensions
            for tracer_name in self.tracer_names():
                if fptr.variables[tracer_name+suffix].dimensions != dimnames0:
                    raise ValueError('not all vars have same dimensions',
                                     'tracer_module_name=', tracer_module_name,
                                     'vals_fname=', vals_fname)
            # read values
            if len(dims) > 3:
                raise ValueError('ndim too large (for implementation of dot_prod)',
                                 'tracer_module_name=', tracer_module_name,
                                 'vals_fname=', vals_fname,
                                 'ndim=', len(dims))
            for tracer_ind, tracer_name in enumerate(self.tracer_names()):
                varid = fptr.variables[tracer_name+suffix]
                vals[tracer_ind, :] = varid[:]
        logger.debug('returning')
        return vals, dims

    def dump(self, fptr, action):
        """
        perform an action (define or write) of dumping a TracerModuleState object
        to an open file
        """
        if action == 'define':
            for dimname, dimlen in self._dims.items():
                try:
                    if fptr.dimensions[dimname].size != dimlen:
                        raise ValueError('dimname already exists and has wrong size',
                                         'tracer_module_name=', self._tracer_module_name,
                                         'dimname=', dimname)
                except KeyError:
                    fptr.createDimension(dimname, dimlen)
            dimnames = tuple(self._dims.keys())
            # define all tracers, with _CUR and _OLD suffixes
            for tracer_name in self.tracer_names():
                for suffix in ['_CUR', '_OLD']:
                    fptr.createVariable(tracer_name+suffix, 'f8', dimensions=dimnames)
        elif action == 'write':
            # write all tracers, with _CUR and _OLD suffixes
            for tracer_ind, tracer_name in enumerate(self.tracer_names()):
                for suffix in ['_CUR', '_OLD']:
                    fptr.variables[tracer_name+suffix][:] = self._vals[tracer_ind, :]
        else:
            raise ValueError('unknown action=', action)
        return self

################################################################################

class NewtonFcn():
    """class of methods related to problem being solved with Newton's method"""
    def __init__(self):
        pass

    def comp_fcn(self, ms_in, res_fname, solver_state, hist_fname=None):
        """evalute function being solved with Newton's method"""
        logger = logging.getLogger(__name__)
        logger.debug('entering')

        _comp_fcn_pre_modelrun(ms_in, res_fname, solver_state)

        _gen_hist(hist_fname)

        ms_res = _comp_fcn_post_modelrun(ms_in)

        logger.debug('returning')
        return ms_res.dump(res_fname)

    def _def_dims(self, fptr_in, fptr_out):
        """define netCDF4 dimensions relevant to cesm_pop"""
        for dimname in ['nlon', 'nlat', 'z_t']:
            fptr_out.createDimension(dimname, fptr_in.dimensions[dimname].size)

    def _precond_fname(self, solver_state):
        """filename of preconditioner of jacobian of comp_fcn."""
        return os.path.join(solver_state.get_workdir(), 'precond.nc')

    def gen_precond_jacobian(self, hist_fname, solver_state):
        """Generate file(s) needed for preconditioner of jacobian of comp_fcn."""
        with Dataset(hist_fname, 'r') as fptr_in, \
                Dataset(self._precond_fname(solver_state), 'w') as fptr_out:
            # define output vars
            self._def_dims(fptr_in, fptr_out)

            for tracer_module_name in get_modelinfo('tracer_module_names').split(',')+['base']:
                tracer_module_def = get_tracer_module_def(tracer_module_name)
                for hist_to_precond_var_name in tracer_module_def['hist_to_precond_var_names']:
                    hist_var_name, _, time_op = hist_to_precond_var_name.partition(':')
                    hist_var = fptr_in.variables[hist_var_name]

                    if time_op not in ['avg', 'log_avg', 'copy', '']:
                        raise ValueError('unknown time_op=%s in %s for %s'
                                         % (time_op, hist_to_precond_var_name, tracer_module_name))

                    if time_op == 'avg':
                        precond_var = fptr_out.createVariable(hist_var_name+'_avg',
                                                              hist_var.datatype,
                                                              dimensions=hist_var.dimensions[1:])
                        precond_var.long_name = hist_var.long_name+', avg over time dim'
                        precond_var[:] = hist_var[:].mean(axis=0)
                    elif time_op == 'log_avg':
                        precond_var = fptr_out.createVariable(hist_var_name+'_log_avg',
                                                              hist_var.datatype,
                                                              dimensions=hist_var.dimensions[1:])
                        precond_var.long_name = hist_var.long_name+', log avg over time dim'
                        precond_var[:] = np.exp(np.log(hist_var[:]).mean(axis=0))
                    else:
                        precond_var = fptr_out.createVariable(hist_var_name,
                                                              hist_var.datatype,
                                                              dimensions=hist_var.dimensions)
                        precond_var.long_name = hist_var.long_name
                        precond_var[:] = hist_var[:]

                    for att_name in ['units', 'coordinates', 'positive']:
                        try:
                            setattr(precond_var, att_name, getattr(hist_var, att_name))
                        except AttributeError:
                            pass

        self._gen_precond_matrix_files(solver_state)

    def _gen_precond_matrix_files(self, solver_state):
        """Generate matrix files for preconditioner of jacobian of comp_fcn."""
        jacobian_precond_tools_dir = get_modelinfo('jacobian_precond_tools_dir')

        tracer_module_base_def = get_tracer_module_def('base')
        matrix_base_opts = tracer_module_base_def['precond_matrices_opts']

        opt_str_subs = {'day_cnt':365*_yr_cnt(),
                        'precond_fname':self._precond_fname(solver_state),
                        'reg_fname':get_modelinfo('region_mask_fname'),
                        'irf_fname':get_modelinfo('irf_fname')}

        for tracer_module_name in get_modelinfo('tracer_module_names').split(','):
            tracer_module_def = get_tracer_module_def(tracer_module_name)
            for matrix_name, matrix_opts in tracer_module_def['precond_matrices_opts'].items():
                matrix_opts_fname = os.path.join(solver_state.get_workdir(),
                                                 'matrix_'+matrix_name+'.opts')
                with open(matrix_opts_fname, 'w') as fptr:
                    for opt in matrix_base_opts+matrix_opts:
                        fptr.write("%s\n" % opt.format(**opt_str_subs))
                matrix_fname = os.path.join(solver_state.get_workdir(),
                                            'matrix_'+matrix_name+'.nc')
                cmd = [os.path.join(jacobian_precond_tools_dir, 'bin', 'gen_A'),
                       '-D1', '-o', matrix_opts_fname, matrix_fname]
                subprocess.run(cmd, check=True)

    def apply_precond_jacobian(self, ms_in, res_fname, solver_state):
        """apply preconditioner of jacobian of comp_fcn to model state object, ms_in"""
        logger = logging.getLogger(__name__)
        logger.debug('entering')

        fcn_complete_step = 'apply_precond_jacobian done for %s' % res_fname
        if solver_state.step_logged(fcn_complete_step):
            logger.debug('"%s" logged, returning result', fcn_complete_step)
            return ModelState(res_fname)
        logger.debug('"%s" not logged, proceeding', fcn_complete_step)

        _apply_precond_jacobian_pre_solve_lin_eqns(res_fname, solver_state)

        lin_eqns_soln_fname = os.path.join(os.path.dirname(res_fname),
                                           'lin_eqns_soln_'+os.path.basename(res_fname))
        ms_res = _apply_precond_jacobian_solve_lin_eqns(ms_in, self._precond_fname(solver_state),
                                                        lin_eqns_soln_fname, solver_state)

        ms_res -= ms_in

        solver_state.log_step(fcn_complete_step)

        logger.debug('returning')
        return ms_res.dump(res_fname)

################################################################################

def _comp_fcn_pre_modelrun(ms_in, res_fname, solver_state):
    """pre-modelrun step of evaluting the function being solved with Newton's method"""
    logger = logging.getLogger(__name__)
    logger.debug('entering')

    fcn_complete_step = '_comp_fcn_pre_modelrun done for %s' % res_fname
    if solver_state.step_logged(fcn_complete_step):
        logger.debug('"%s" logged, returning', fcn_complete_step)
        return
    logger.debug('"%s" not logged, proceeding', fcn_complete_step)

    # relative pathname of tracer_ic
    tracer_ic_fname_rel = 'tracer_ic.nc'
    fname = os.path.join(_xmlquery('RUNDIR'), tracer_ic_fname_rel)
    ms_in.dump(fname)

    # ensure certain env xml vars are set properly
    _xmlchange('POP_PASSIVE_TRACER_RESTART_OVERRIDE', tracer_ic_fname_rel)
    _xmlchange('CONTINUE_RUN', 'FALSE')

    # copy rpointer files to rundir
    rundir = _xmlquery('RUNDIR')
    for src in glob.glob(os.path.join(get_modelinfo('rpointer_dir'), 'rpointer.*')):
        shutil.copy(src, rundir)

    # generate post-modelrun script and point POSTRUN_SCRIPT to it
    # this will propagate cfg_fname and hist_fname across model run
    cwd = os.path.dirname(os.path.realpath(__file__))
    post_modelrun_script_fname = os.path.join(cwd, 'generated_scripts', 'post_modelrun.sh')
    _gen_post_modelrun_script(post_modelrun_script_fname)
    _xmlchange('POSTRUN_SCRIPT', post_modelrun_script_fname)

    # submit the model run and exit
    _case_submit()

    solver_state.log_step(fcn_complete_step)

    logger.debug('raising SystemExit')
    raise SystemExit

def _gen_post_modelrun_script(script_fname):
    """
    generate script that will be called by cime after the model run
    script_fname is called by CIME, and submits nk_driver_invoker_fname with the command
        batch_cmd_script (which can be an empty string)
    """
    cwd = os.path.dirname(os.path.realpath(__file__))
    batch_cmd_script = get_modelinfo('batch_cmd_script').replace('\n', ' ').replace('\r', ' ')
    with open(script_fname, mode='w') as fptr:
        fptr.write('#!/bin/bash\n')
        fptr.write('cd %s\n' % cwd)
        fptr.write('%s %s --resume\n' % (batch_cmd_script,
                                         get_modelinfo('nk_driver_invoker_fname')))

    # ensure script_fname is executable by the user, while preserving other permissions
    fstat = os.stat(script_fname)
    os.chmod(script_fname, fstat.st_mode | stat.S_IXUSR)

def _yr_cnt():
    """return how many years are in forward model run"""
    stop_option = _xmlquery('STOP_OPTION')
    stop_n = int(_xmlquery('STOP_N'))
    if stop_option == 'nyear':
        yr_cnt = stop_n
    elif stop_option == 'nmonth':
        if stop_n % 12 != 0:
            raise RuntimeError('number of months=%d not divisible by 12' % stop_n)
        yr_cnt = int(stop_n) // 12
    else:
        raise NotImplementedError('stop_option = %s not implemented' % stop_option)
    return yr_cnt

def _gen_hist(hist_fname):
    """generate history file corresponding to just completed model run"""
    logger = logging.getLogger(__name__)

    if hist_fname is None:
        return

    # initial implementation only works for annual mean output
    # confirm that this is the case
    tavg_freq_opt_0 = _get_pop_nl_var('tavg_freq_opt').split()[0].split("'")[1]
    if tavg_freq_opt_0 != 'nyear':
        raise NotImplementedError('tavg_freq_opt_0 = %s not implemented' % tavg_freq_opt_0)

    tavg_freq_0 = _get_pop_nl_var('tavg_freq').split()[0]
    if tavg_freq_0 != '1':
        raise NotImplementedError('tavg_freq_0 = %s not implemented' % tavg_freq_0)

    # get starting year
    if _xmlquery('RUN_TYPE') == 'branch':
        date0 = _xmlquery('RUN_REFDATE')
    else:
        date0 = _xmlquery('RUN_STARTDATE')
    yyyy = date0.split('-')[0]

    # construct name of first annual file
    if _xmlquery('DOUT_S') == 'TRUE':
        hist_dir = os.path.join(_xmlquery('DOUT_S_ROOT'), 'ocn', 'hist')
    else:
        hist_dir = _xmlquery('RUNDIR')
    model_hist_fname = os.path.join(hist_dir, _xmlquery('CASE')+'.pop.h.'+yyyy+'.nc')

    cmd = ['ncra', '-O', '-n', '%d,4' % _yr_cnt(), '-o', hist_fname, model_hist_fname]
    logger.debug('cmd = "%s"', ' '.join(cmd))
    subprocess.run(cmd, check=True)

def _comp_fcn_post_modelrun(ms_in):
    """post-modelrun step of evaluting the function being solved with Newton's method"""

    # determine name of end of run restart file from POP's rpointer file
    rpointer_fname = os.path.join(_xmlquery('RUNDIR'), 'rpointer.ocn.restart')
    with open(rpointer_fname, mode='r') as fptr:
        rest_file_fname_rel = fptr.readline().strip()
    fname = os.path.join(_xmlquery('RUNDIR'), rest_file_fname_rel)

    return ModelState(fname) - ms_in

def _apply_precond_jacobian_pre_solve_lin_eqns(res_fname, solver_state):
    """
    pre-solve_lin_eqns step of apply_precond_jacobian
    produce computing environment for solve_lin_eqns
    If batch_cmd_precond is non-empty, submit a batch job using that command and exit.
    Otherwise, just return.
    """
    logger = logging.getLogger(__name__)
    logger.debug('entering')

    fcn_complete_step = '_apply_precond_jacobian_pre_solve_lin_eqns done for %s' % res_fname
    if solver_state.step_logged(fcn_complete_step):
        logger.debug('"%s" logged, returning', fcn_complete_step)
        return
    logger.debug('"%s" not logged, proceeding', fcn_complete_step)

    if get_modelinfo('batch_cmd_precond'):
        precond_task_cnt = int(get_modelinfo('precond_task_cnt'))
        precond_cpus_per_node = int(get_modelinfo('precond_cpus_per_node'))
        precond_node_cnt = int(np.ceil(precond_task_cnt / precond_cpus_per_node))
        opt_str_subs = {'precond_node_cnt':precond_node_cnt}
        batch_cmd = get_modelinfo('batch_cmd_precond').replace('\n', ' ').replace('\r', ' ')
        cmd = '%s %s --resume' % (batch_cmd.format(**opt_str_subs),
                                  get_modelinfo('nk_driver_invoker_fname'))
        subprocess.run(cmd, check=True, shell=True)
        solver_state.log_step(fcn_complete_step)
        logger.debug('raising SystemExit')
        raise SystemExit

    solver_state.log_step(fcn_complete_step)
    logger.debug('returning')

def _apply_precond_jacobian_solve_lin_eqns(ms_in, precond_fname, res_fname, solver_state):
    """
    solve_lin_eqns step of apply_precond_jacobian
    """
    logger = logging.getLogger(__name__)
    logger.debug('entering')

    fcn_complete_step = '_apply_precond_jacobian_solve_lin_eqns done for %s' % res_fname
    if solver_state.step_logged(fcn_complete_step):
        logger.debug('"%s" logged, returning', fcn_complete_step)
        return ModelState(res_fname)
    logger.debug('"%s" not logged, proceeding', fcn_complete_step)

    ms_in.dump(res_fname)

    jacobian_precond_tools_dir = get_modelinfo('jacobian_precond_tools_dir')

    # determine size of decomposition to be used in matrix factorization
    nprow, npcol = _matrix_block_decomp()

    for tracer_module_name in get_modelinfo('tracer_module_names').split(','):
        tracer_module_def = get_tracer_module_def(tracer_module_name)
        for matrix_name, matrix_opts in tracer_module_def['precond_matrices_opts'].items():
            matrix_fname = os.path.join(solver_state.get_workdir(),
                                        'matrix_'+matrix_name+'.nc')
            cmd = [get_modelinfo('mpi_cmd'),
                   os.path.join(jacobian_precond_tools_dir, 'bin', 'solve_ABdist'),
                   '-D1', '-n', '%d,%d' % (nprow, npcol),
                   '-v', _tracer_names_str(matrix_name, matrix_opts),
                   matrix_fname, res_fname]
            subprocess.run(cmd, check=True)

            _apply_tracers_sflux_term(tracer_module_def, matrix_name, matrix_opts, precond_fname,
                                      res_fname)

    ms_res = ModelState(res_fname)

    solver_state.log_step(fcn_complete_step)
    logger.debug('returning')
    return ms_res

def _matrix_block_decomp():
    """determine size of decomposition to be used in matrix factorization"""
    precond_task_cnt = int(get_modelinfo('precond_task_cnt'))
    log2_precond_task_cnt = int(np.log(precond_task_cnt)/np.log(2.0))
    if 2 ** log2_precond_task_cnt != precond_task_cnt:
        raise ValueError('precond_task_cnt must be a power of 2')
    if (log2_precond_task_cnt % 2) == 0:
        nprow = 2 ** (log2_precond_task_cnt // 2)
        npcol = nprow
    else:
        nprow = 2 ** ((log2_precond_task_cnt-1) // 2)
        npcol = 2 * nprow
    return nprow, npcol

def _tracer_names_list(matrix_name, matrix_opts):
    """list of tracers being solved for"""
    # If there is a tracer_names option in matrix_opts, use that,
    # otherwise use the name of the matrix.
    tracer_names = None
    for matrix_opt in matrix_opts:
        if 'tracer_names' in matrix_opt:
            tracer_names = matrix_opt.split()[1:]
    if tracer_names is None:
        tracer_names = [matrix_name]
    return tracer_names

def _tracer_names_str(matrix_name, matrix_opts):
    """comma seperated string of tracers being solved for"""
    return ','.join([tracer_name+'_CUR' for tracer_name \
                     in _tracer_names_list(matrix_name, matrix_opts)])

def _apply_tracers_sflux_term(tracer_module_def, matrix_name, matrix_opts, precond_fname,
                              res_fname):
    """apply surface flux term of tracers in tracer_names_list to subsequent vars"""
    model_state = ModelState(res_fname)
    term_applied = False
    delta_time = 365.0 * 86400.0 * _yr_cnt()
    with Dataset(precond_fname, 'r') as fptr:
        for tracer_name_src in _tracer_names_list(matrix_name, matrix_opts):
            src = model_state.get_tracer_vals(tracer_name_src)
            for tracer_name_dst_ind in \
                    range(tracer_module_def['tracer_names'].index(tracer_name_src)+1,
                          len(tracer_module_def['tracer_names'])):
                tracer_name_dst = tracer_module_def['tracer_names'][tracer_name_dst_ind]
                var_name = 'd_SF_'+tracer_name_dst+'_d_'+tracer_name_src+':avg'
                if var_name in fptr.variables:
                    dst = model_state.get_tracer_vals(tracer_name_dst)
                    dst[0, :] -= delta_time / fptr.variables['dz'][0] \
                        * fptr.variables[var_name][:] * src[0, :]
                    model_state.set_tracer_vals(tracer_name_dst, dst)
                    term_applied = True
    if term_applied:
        model_state.dump(res_fname)

def _xmlquery(varname):
    """run CIME's _xmlquery for varname in the directory caseroot, return the value"""
    caseroot = get_modelinfo('caseroot')
    return subprocess.check_output(['./xmlquery', '--value', varname], cwd=caseroot).decode()

def _xmlchange(varname, value):
    """run CIME's _xmlchange in the directory caseroot, setting varname to value"""
    # skip change command if it would not change the value
    # this avoids clutter in the file CaseStatus
    if value != _xmlquery(varname):
        caseroot = get_modelinfo('caseroot')
        subprocess.run(['./xmlchange', '%s=%s' % (varname, value)], cwd=caseroot, check=True)

def _case_submit():
    """submit a CIME case, return after submit completes"""
    logger = logging.getLogger(__name__)

    cwd = os.path.dirname(os.path.realpath(__file__))
    script_fname = os.path.join(cwd, 'generated_scripts', 'case_submit.sh')
    with open(script_fname, mode='w') as fptr:
        fptr.write('#!/bin/bash\n')
        fptr.write('source %s\n' % get_modelinfo('cime_env_cmds_fname'))
        fptr.write('cd %s\n' % get_modelinfo('caseroot'))
        fptr.write('./case.submit\n')

    # ensure script_fname is executable by the user, while preserving other permissions
    fstat = os.stat(script_fname)
    os.chmod(script_fname, fstat.st_mode | stat.S_IXUSR)

    logger.info('submitting case=%s', _xmlquery('CASE'))
    subprocess.run(script_fname, shell=True, check=True)

def _get_pop_nl_var(var_name):
    """
    extract the value(s) of a pop namelist variable
    return contents to the right of the '=' character,
        after stripping leading and trailing whitespace, and replacing ',' with ' '
    can lead to unexpected results if the rhs has strings with commas
    does not handle multiple matches of var_name in pop_in
    """
    nl_fname = os.path.join(get_modelinfo('caseroot'), 'CaseDocs', 'pop_in')
    cmd = ['grep', '^ *'+var_name+' *=', nl_fname]
    line = subprocess.check_output(cmd).decode()
    return line.split('=')[1].strip().replace(',', ' ')

if __name__ == '__main__':
    main(_parse_args())
