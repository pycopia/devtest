# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Universal constants and enumerations. These may be used in code, and are
also translated to enumerations or integers in persistent storage.
"""

from .types import Enum


class TestResult(Enum):
    """The outcome of a test case."""
    NA = -1
    # These values are chosen for "truthiness" if passed back to a shell.
    PASSED = 0  # A test was run and it indicated the feature passed the test.
    FAILED = 1  # A test was run and it indicated the feture did not pass the test.
    INCOMPLETE = 2  # The test was run, but did not complete and outcome can't be determined.
    SKIPPED = 3  # The test was never started, skipped by the framework.
    EXPECTED_FAIL = 5  # The test was run and feature did not pass, that that is expected.
    ABORTED = 6  # The test started but the user or framework interrupted the test.

    def is_passed(self):
        return self.value == TestResult.PASSED

    def not_passed(self):
            return self.value in (TestResult.FAILED, TestResult.EXPECTED_FAIL,
                                  TestResult.SKIPPED, TestResult.INCOMPLETE,
                                  TestResult.ABORT)

    def is_failed(self):
        return self.value == TestResult.FAILED

    def is_incomplete(self):
        return self.value == TestResult.INCOMPLETE

    def __bool__(self):
        return self.value == TestResult.PASSED


class TestResultType(Enum):
    """Types of objects that have test result records."""
    Unknown = 0
    Test = 1
    TestSuite = 2
    Scenario = 3
    TestRunSummary = 4


class TestCaseType(Enum):
    """Type of test case, where it fits in the development cycle."""
    Unknown = 0
    Unit = 1
    System = 2
    Integration = 3
    Regression = 4
    Performance = 5
    Functional = 6
    Acceptance = 7
    Component = 8
    Utility = 9


class TestCaseStatus(Enum):
    """Status of a test case itself."""
    Unknown = 0
    New = 1
    Reviewed = 2
    Preproduction = 3
    Production = 4
    Deprecated = 5
    Obsolete = 6


class Priority(Enum):
    """Priority of something, such as a test case."""
    Unknown = 0
    P1 = 1
    P2 = 2
    P3 = 3
    P4 = 4
    P5 = 5


class ConnectionType(Enum):
    """Type of equipment connections. For non-network, point-to-point
    connections.
    """
    Unknown = 0
    Serial = 1
    USB2 = 2
    USB3 = 3
    Firewire = 4
    Lightning = 5
    Thunderbolt = 6
    JTAG = 7
    Bluetooth = 8
    Power = 9


class NetworkType(Enum):
    """Type of data network. For Network objects.
    Values match IANA defined types (ifType) in IANAifType-MIB.
    """
    Unknown = 0
    Ethernet = 6
    FibreChannel = 56
    Wifi = 71
    Tunnel = 131
    Vlan = 135
    USB = 160
    Aggregate = 161
    # BSD derived
    Dummy = 241
    Bluetooth = 248

# vim:ts=4:sw=4:softtabstop=4:smarttab:expandtab
