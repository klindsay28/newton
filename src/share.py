"""functions shared across multiple modules"""

import argparse
import configparser
import os

import git

from .utils import mkdir_exist_okay

cfg_override_args = {
    "workdir": {"section": "DEFAULT"},
    "logging_level": {"section": "solverinfo"},
    "newton_max_iter": {"section": "solverinfo"},
    "newton_rel_tol": {"section": "solverinfo"},
    "tracer_module_names": {"section": "modelinfo"},
    "persist": {
        "model_name": "test_problem",
        "override_var": "reinvoke",
        "action": "store_true",
        "override_val": "False",
        "section": "modelinfo",
    },
}


def common_args(description, model_name="test_problem"):
    """instantiate and return a parser, using common options"""
    parser = argparse.ArgumentParser(
        description=description, formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--cfg_fname",
        help="name of configuration file",
        default="models/%s/newton_krylov.cfg" % model_name,
    )

    # add arguments that override cfg file
    for argname, metadata in cfg_override_args.items():
        # skip arguments that are model specific for a different model_name
        if "model_name" in metadata and model_name != metadata["model_name"]:
            continue
        override_var = metadata.get("override_var", argname)
        if "action" not in metadata:
            parser.add_argument(
                "--%s" % argname,
                help="override %s from cfg file" % override_var,
                default=None,
            )
        elif metadata["action"] in ["store_true"]:
            parser.add_argument(
                "--%s" % argname,
                help="override %s from cfg file" % override_var,
                action=metadata["action"],
            )
        else:
            msg = "action = %s not implemented" % metadata["action"]
            raise NotImplementedError(msg)

    return parser


def args_replace(args, model_name=None):
    """apply common args replacements/format on string arguments"""
    model_name_repl = getattr(args, "model_name", model_name)
    if "model_name" is None:
        raise ValueError("model_name is None")
    # pass "{suff}" through
    str_subs = {"model_name": model_name_repl, "suff": "{suff}"}
    for arg, value in vars(args).items():
        if isinstance(value, str):
            setattr(args, arg, value.format(**str_subs))
    return args


def read_cfg_file(args):
    """
    read cfg file
    set defaults common to all occurrances
    """
    cfg_fname = args.cfg_fname

    defaults = {key: os.environ[key] for key in ["HOME", "USER"]}
    defaults["repo_root"] = git.Repo(search_parent_directories=True).working_dir
    config = configparser.ConfigParser(defaults, allow_no_value=True)
    config.read_file(open(cfg_fname))

    # verify that only names in no_value_allowed have no value
    # no_value_allowed is allowed to have no value or not be present
    if "no_value_allowed" in config["DEFAULT"]:
        no_value_allowed = config["DEFAULT"]["no_value_allowed"]
    else:
        no_value_allowed = None
    nva_list = [] if no_value_allowed is None else no_value_allowed.split(",")
    nva_list.append("no_value_allowed")
    for section in config.sections():
        for name in config[section]:
            if config[section][name] is None and name not in nva_list:
                msg = "%s not allowed to be empty in cfg file %s" % (name, cfg_fname)
                raise ValueError(msg)

    # apply arguments that override cfg file
    for argname, metadata in cfg_override_args.items():
        # skip conditional overrides that were not added
        if argname not in args:
            continue
        override_var = metadata.get("override_var", argname)
        if override_var not in config[metadata["section"]]:
            msg = "%s not in cfg section %s" % (override_var, metadata["section"])
            raise ValueError(msg)
        if "action" not in metadata:
            if getattr(args, argname) is not None:
                config[metadata["section"]][override_var] = getattr(args, argname)
        elif metadata["action"] == "store_true":
            if getattr(args, argname):
                config[metadata["section"]][override_var] = metadata["override_val"]

    # write cfg contents to a file, if requested
    cfg_out_fname = config["solverinfo"]["cfg_out_fname"]
    if cfg_out_fname is not None:
        mkdir_exist_okay(os.path.dirname(cfg_out_fname))
        with open(cfg_out_fname, "w") as fptr:
            config.write(fptr)

    return config
