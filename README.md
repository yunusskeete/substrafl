# ConnectLib

## Installation

With pip >= 21.2.0:

```bash
# Uses Owkin private Pypi repository, if you do not have credentials ask Olivier Léobal: olivier.leobal@owkin.com
# Please setup the credentials once and for all in your ~/.pip/pip.conf file as followed :

# For basic install
[global]
extra-index-url = https://<username>:<password>@pypi.owkin.com/simple
```

## Contribute

ConnectLib is open to contributions. Please have a look at the [Contribution Guidelines](https://owkin-connectlib.readthedocs-hosted.com/en/latest/contribute/contribution_process.html).

## Release

See the release process on the tech-team [releasing guide](https://github.com/owkin/tech-team/blob/main/releasing_guide.md#connectlib).

## Documentation

Documentation of the api is generated from the connectlib repository thanks to the auto doc module.

### Requirements

You need to have connectlib.dev installed on your machine and some extra requirements. From the connectlib repo:

```sh
pip install -e .[dev]
cd docs
pip install -r requirements.txt
```

### Building the documentation

You can build the documentation to see if your changes are well taken into account.
From ./docs folder :

```sh
make clean && make html
```

No warning should be thrown by this command.

Then open the `./docs/_build/index.html` file to see the results.

You can also generate the documentation live so each of your changes are taken into account on the fly:

```sh
make livehtml
```

NB: Some time, `make livehtml` do not taken changes into account so running the `make html` command in parallel can be needed.

## Implementing a new strategy

### Kick-off

Define the people involved in the implementation of the strategy:

- **referent**: a data scientist from the FL group, available for questions and discussion
- **developer**: the developer who implements the FL strategy
- **primary reviewer**: discusses the strategy with the developer, helps in the design phase and implements the tests
- **secondary reviewers**: members of the FLow squad who review the design and implementation. Should be at least 2 people.

For "simple" strategies, the primary reviewer may be optional.

### Design phase

The design phase is to understand the strategy, discuss the implementation and define how to test it.

The **developer** reads the scientific paper and consults existing implementations (e.g. in Ruche). He
discusses with the **referent** to ensure he understands the strategy correctly.

If there are several possible implementations or implicit choices in the paper, the **developer** defines
with the **referent** what is necessary for the end user a.k.a the data scientist.

The **developer** discusses the design with the **primary reviewer**, the **primary reviewer** designs the tests.

The output of the design phase is:
- a description of the FL strategy in [connect-documentation](https://github.com/owkin/connect-documentation/blob/main/docs/source/connectlib/index.rst)
- an open PR on the [connectlib](https://github.com/owkin/connectlib) repository, with in the description:
  - the list of changes to do to implement the strategy, with special emphasis on sensitive points
  - the docstring of the algo, and the docstring of the strategy
  - a description of the tests
  - a link to the documentation

The design phase is validated by the **referent** and the **secondary reviewers**.

### Implementation

The **developer** and the **primary reviewer** work together to implement the strategy.

The **developer** implements the strategy itself while the **primary reviewer** implements the tests.
Any design question that arises during the implementation phase must be discussed with the **referent**.

**WARNING**: no untested code can be merged into the main branch, so the tests and strategy cannot be merged separately
into the main branch. It is up to the **developer** and **primary reviewer** to decide how to work together (same branch
or 2 branches merged together to form one pull request).

The **secondary reviewers** review the pull request, they validate both the scientific and engineering sides of the implementation.

The implementation phases ends with the merge of the pull request. The strategy is now considered as released
and usable, there should be no "TODOs" left.

#### How to

A few points on the implementation itself:

- reading pre-existing code may help understand the strategy however copy-pasting is strongly discouraged, the **developer**
    is responsible of the validity of the implementation and should have a deep understanding of every step.
- the strategy must be usable with any framework i.e. it must be possible to create a tensorFlow or scikit-learn layer without
    changing the strategy code
- torch algo layer:
  - the `__init__` function is called once on the user's computer and at the beginning of each round: avoid costly operations
  - the `load` and `save` functions manage the local state i.e. the parameters that must be passed from one round to the next
  - the `_local_train` and `_local_predict` functions must be overwritten by the user so they contain as little strategy-specific code as possible

#### Tests

Test the "strategy" part.

Create an end-to-end test for each algo layer of the strategy, with an assert on a given performance. The end-to-end test runs only during
the nightly CI run.

### Scientific review

Once the implementation phase is over, the **developer** asks the **referent** for a scientific review.
The **referent** has two weeks to go over the PR once it is merged. The review by the **referent** includes:

- checking the mathematical and algorithmic validity of the implementation
- asking to add some tests on corner cases
- pointing out inefficiencies: eg a matrix multiplication is very slow because of the implementation

The **referent** should be as clear as possible to avoid going back and forth between **referent** and **developer**.
If necessary, the **referent** can propose a call with the **developer**.
