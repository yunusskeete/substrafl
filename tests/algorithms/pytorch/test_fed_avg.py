import logging

import pytest
import torch

from substrafl import execute_experiment
from substrafl.algorithms.pytorch import TorchFedAvgAlgo
from substrafl.algorithms.pytorch.weight_manager import increment_parameters
from substrafl.dependency import Dependency
from substrafl.evaluation_strategy import EvaluationStrategy
from substrafl.index_generator import NpIndexGenerator
from substrafl.model_loading import download_algo_files
from substrafl.model_loading import load_algo
from substrafl.strategies import FedAvg
from tests import utils
from tests.algorithms.pytorch.torch_tests_utils import assert_model_parameters_equal

logger = logging.getLogger(__name__)


EXPECTED_PERFORMANCE = 0.0127768361


@pytest.fixture(scope="module")
def torch_algo(torch_linear_model, numpy_torch_dataset, seed):
    num_updates = 100
    torch.manual_seed(seed)
    perceptron = torch_linear_model()
    nig = NpIndexGenerator(
        batch_size=32,
        num_updates=num_updates,
    )

    class MyAlgo(TorchFedAvgAlgo):
        def __init__(
            self,
        ):
            super().__init__(
                optimizer=torch.optim.SGD(perceptron.parameters(), lr=0.1),
                criterion=torch.nn.MSELoss(),
                model=perceptron,
                index_generator=nig,
                dataset=numpy_torch_dataset,
            )

    return MyAlgo


@pytest.fixture(scope="module")
def compute_plan(torch_algo, train_linear_nodes, test_linear_nodes, aggregation_node, network, session_dir):
    NUM_ROUNDS = 3

    algo_deps = Dependency(
        pypi_dependencies=["torch", "numpy"],
        editable_mode=True,
    )

    strategy = FedAvg(algo=torch_algo())
    my_eval_strategy = EvaluationStrategy(
        test_data_nodes=test_linear_nodes, eval_rounds=[0, NUM_ROUNDS]
    )  # test the initialization and the last round

    compute_plan = execute_experiment(
        client=network.clients[0],
        strategy=strategy,
        train_data_nodes=train_linear_nodes,
        evaluation_strategy=my_eval_strategy,
        aggregation_node=aggregation_node,
        num_rounds=NUM_ROUNDS,
        dependencies=algo_deps,
        experiment_folder=session_dir / "experiment_folder",
        clean_models=False,
    )

    # Wait for the compute plan to be finished
    utils.wait(network.clients[0], compute_plan)

    return compute_plan


@pytest.mark.substra
@pytest.mark.slow
def test_pytorch_fedavg_algo_weights(network, compute_plan, torch_algo, session_dir):
    """Check the weight initialization, aggregation and set weights.
    The aggregation itself is tested at the strategy level, here we test
    the pytorch layer.
    """

    my_algo = torch_algo()

    rank_1_local_models = utils.download_composite_models_by_rank(network, session_dir, my_algo, compute_plan, rank=1)
    rank_3_local_models = utils.download_composite_models_by_rank(network, session_dir, my_algo, compute_plan, rank=3)

    # Download the aggregate output
    aggregate_model = utils.download_aggregate_model_by_rank(network, session_dir, compute_plan, rank=2)
    aggregate_update = [torch.from_numpy(x).to("cpu") for x in aggregate_model.avg_parameters_update]

    # Assert the model initialization is the same for every model
    assert_model_parameters_equal(rank_1_local_models[0].model, rank_3_local_models[1].model)

    # Assert that the weights are well set
    for model_1, model_3 in zip(rank_1_local_models, rank_3_local_models):
        increment_parameters(model_1.model, aggregate_update, with_batch_norm_parameters=True)
        assert_model_parameters_equal(model_1.model, model_3.model)

    # The local models are always the same on every organization
    assert_model_parameters_equal(rank_3_local_models[0].model, rank_3_local_models[1].model)


@pytest.mark.e2e
@pytest.mark.substra
@pytest.mark.slow
def test_pytorch_fedavg_algo_performance(
    network,
    compute_plan,
    torch_linear_model,
    test_linear_data_samples,
    mae,
    rtol,
    seed,
):
    """End to end test for torch fed avg algorithm."""

    perfs = network.clients[0].get_performances(compute_plan.key)
    assert pytest.approx(EXPECTED_PERFORMANCE, rel=rtol) == perfs.performance[1]

    torch.manual_seed(seed)

    model = torch_linear_model()
    y_pred = model(torch.from_numpy(test_linear_data_samples[0][:, :-1]).float()).detach().numpy().reshape(-1)
    y_true = test_linear_data_samples[0][:, -1]

    performance_at_init = mae(y_pred, y_true)
    assert performance_at_init == pytest.approx(perfs.performance[0], abs=rtol)


@pytest.mark.e2e
@pytest.mark.slow
@pytest.mark.substra
def test_download_load_algo(network, compute_plan, session_dir, test_linear_data_samples, mae, rtol):
    download_algo_files(
        client=network.clients[0],
        compute_plan_key=compute_plan.key,
        round_idx=None,
        dest_folder=session_dir,
    )
    model = load_algo(input_folder=session_dir)._model

    y_pred = model(torch.from_numpy(test_linear_data_samples[0][:, :-1]).float()).detach().numpy().reshape(-1)
    y_true = test_linear_data_samples[0][:, -1]
    performance = mae(y_pred, y_true)

    assert performance == pytest.approx(EXPECTED_PERFORMANCE, rel=rtol)
