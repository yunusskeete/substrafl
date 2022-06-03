from typing import List
from typing import Optional

import numpy as np

from connectlib.algorithms.algo import Algo
from connectlib.nodes.aggregation_node import AggregationNode
from connectlib.nodes.references.local_state import LocalStateRef
from connectlib.nodes.references.shared_state import SharedStateRef
from connectlib.nodes.test_data_node import TestDataNode
from connectlib.nodes.train_data_node import TrainDataNode
from connectlib.remote import remote
from connectlib.schemas import FedAvgAveragedState
from connectlib.schemas import FedAvgSharedState
from connectlib.schemas import StrategyName
from connectlib.strategies.strategy import Strategy


class FedAvg(Strategy):
    """Federated averaging strategy.

    Federated averaging is the simplest federating strategy.
    A round consists in performing a predefined number of forward/backward
    passes on each client, aggregating updates by computing their means and
    distributing the consensus update to all clients. In FedAvg, strategy is
    performed in a centralized way, where a single server or
    ``AggregationNode`` communicates with a number of clients ``TrainDataNode``
    and ``TestDataNode``.

    Formally, if :math:`w_t` denotes the parameters of the model at round
    :math:`t`, a single round consists in the following steps:

    .. math::

      \\Delta w_t^{k} = \\mathcal{O}^k_t(w_t| X_t^k, y_t^k, m)
      \\Delta w_t = \\sum_{k=1}^K \\frac{n_k}{n} \\Delta w_t^k
      w_{t + 1} = w_t + \\Delta w_t

    where :math:`\\mathcal{O}^k_t` is the local optimizer algorithm of client
    :math:`k` taking as argument the averaged weights as well as the
    :math:`t`-th batch of data for local worker :math:`k` and the number of
    local updates :math:`m` to perform, and where :math:`n_k` is the number of
    samples for worker :math:`k`, :math:`n = \\sum_{k=1}^K n_k` is the total
    number of samples.
    """

    def __init__(self):
        super(FedAvg, self).__init__()

        # current local and share states references of the client
        self._local_states: Optional[List[LocalStateRef]] = None
        self._shared_states: Optional[List[SharedStateRef]] = None

    @property
    def name(self) -> StrategyName:
        """The name of the strategy

        Returns:
            StrategyName: Name of the strategy
        """
        return StrategyName.FEDERATED_AVERAGING

    @remote
    def avg_shared_states(self, shared_states: List[FedAvgSharedState]) -> FedAvgAveragedState:
        """Compute the weighted average of all elements returned by the train
        methods of the user-defined algorithm.
        The average is weighted by the proportion of the number of samples.

        Example:

            .. code-block:: python

                shared_states = [
                    {"weights": [3, 3, 3], "gradient": [4, 4, 4], "n_samples": 20},
                    {"weights": [6, 6, 6], "gradient": [1, 1, 1], "n_samples": 40},
                ]
                result = {"weights": [5, 5, 5], "gradient": [2, 2, 2]}

        Args:
            shared_states (typing.List[FedAvgSharedState]): The list of the
                shared_state returned by the train method of the algorithm for each node.

        Raises:
            TypeError: The train method of your algorithm must return a shared_state
            TypeError: Each shared_state must contains the key **n_samples**
            TypeError: Each shared_state must contains at least one element to average
            TypeError: All the elements of shared_states must be similar (same keys)
            TypeError: All elements to average must be of type np.ndarray

        Returns:
            FedAvgAveragedState: A dict containing the weighted average of each input parameters
            without the passed key "n_samples".
        """
        if len(shared_states) == 0:
            raise TypeError(
                "Your shared_states is empty. Please ensure that "
                "the train method of your algorithm returns a FedAvgSharedState object."
            )

        assert all(
            [
                len(shared_state.parameters_update) == len(shared_states[0].parameters_update)
                for shared_state in shared_states
            ]
        ), "Not the same number of layers for every input parameters."

        n_all_samples = sum([state.n_samples for state in shared_states])

        averaged_states = list()
        for idx in range(len(shared_states[0].parameters_update)):
            states = list()
            for state in shared_states:
                states.append(state.parameters_update[idx] * (state.n_samples / n_all_samples))
            averaged_states.append(np.sum(states, axis=0))

        return FedAvgAveragedState(avg_parameters_update=averaged_states)

    def _perform_local_updates(
        self,
        algo: Algo,
        train_data_nodes: List[TrainDataNode],
        current_aggregation: Optional[SharedStateRef],
        round_idx: int,
    ):
        """Perform a local update (train on n mini-batches) of the models
        on each train data nodes.

        Args:
            algo (Algo): User defined algorithm: describes the model train and predict methods
            train_data_nodes (typing.List[TrainDataNode]): List of the nodes on which to perform local updates
            current_aggregation (SharedStateRef, Optional): Reference of an aggregation operation to
                be passed as input to each local training
            round_idx (int): Round number, it starts by zero.
        """

        next_local_states = []
        next_shared_states = []

        for i, node in enumerate(train_data_nodes):
            # define composite tuples (do not submit yet)
            # for each composite tuple give description of Algo instead of a key for an algo
            next_local_state, next_shared_state = node.update_states(
                algo.train(  # type: ignore
                    node.data_sample_keys,
                    shared_state=current_aggregation,
                    _algo_name=f"Training with {algo.__class__.__name__}",
                ),
                local_state=self._local_states[i] if self._local_states is not None else None,
                round_idx=round_idx,
            )
            # keep the states in a list: one/node
            next_local_states.append(next_local_state)
            next_shared_states.append(next_shared_state)

        self._local_states = next_local_states
        self._shared_states = next_shared_states

    def perform_round(
        self,
        algo: Algo,
        train_data_nodes: List[TrainDataNode],
        aggregation_node: AggregationNode,
        round_idx: int,
    ):
        """One round of the Federated Averaging strategy consists in:
            - if ``round_ids==0``: initialize the strategy by performing a local update
                (train on n mini-batches) of the models on each train data nodes
            - aggregate the model shared_states
            - set the model weights to the aggregated weights on each train data nodes
            - perform a local update (train on n mini-batches) of the models on each train data nodes

        Args:
            algo (Algo): User defined algorithm: describes the model train and predict methods
            train_data_nodes (typing.List[TrainDataNode]): List of the nodes on which to perform local updates
            aggregation_node (AggregationNode): Node without data, used to perform operations on the shared states
                of the models
            round_idx (int): Round number, it starts by zero.
        """
        if aggregation_node is None:
            raise ValueError("In FedAvg strategy aggregation node cannot be None")

        if round_idx == 0:
            # Initialization of the strategy by performing a local update on each train data node
            assert self._local_states is None
            assert self._shared_states is None
            self._perform_local_updates(
                algo=algo, train_data_nodes=train_data_nodes, current_aggregation=None, round_idx=-1
            )

        current_aggregation = aggregation_node.update_states(
            self.avg_shared_states(shared_states=self._shared_states, _algo_name="Aggregating"),  # type: ignore
            round_idx=round_idx,
        )

        self._perform_local_updates(
            algo=algo, train_data_nodes=train_data_nodes, current_aggregation=current_aggregation, round_idx=round_idx
        )

    def predict(
        self,
        test_data_nodes: List[TestDataNode],
        train_data_nodes: List[TrainDataNode],
        round_idx: int,
    ):

        for test_node in test_data_nodes:
            matching_train_nodes = [
                train_node for train_node in train_data_nodes if train_node.node_id == test_node.node_id
            ]
            if len(matching_train_nodes) == 0:
                raise NotImplementedError("Cannot test on a node we did not train on for now.")

            train_node = matching_train_nodes[0]
            node_index = train_data_nodes.index(train_node)
            assert self._local_states is not None, "Cannot predict if no training has been done beforehand."
            local_state = self._local_states[node_index]

            test_node.update_states(
                traintuple_id=local_state.key,
                round_idx=round_idx,
            )  # Init state for testtuple
