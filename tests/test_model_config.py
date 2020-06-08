"""test functions in model_config.py"""

from src import model_config
from src.model_config import ModelConfig
from src.share import common_args, read_cfg_file


def test_model_config():
    """create ModelConfig object and confirm that model_config_obj is created"""
    parser, args_remaining = common_args("test_model_config", "test_problem", [])
    args = parser.parse_args(args_remaining)
    config = read_cfg_file(args)
    ModelConfig(config["modelinfo"])

    assert model_config.model_config_obj is not None