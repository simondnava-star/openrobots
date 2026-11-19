from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

FILES = {
    "openrobots/README.md": """\
# OpenRobots

An extensible, simulator-first Python framework for connecting different
kinds of robots through one consistent interface. This starter project
includes a harmless simulator, not real robot drivers or unsupervised
physical control.

## Requirements

Python 3.11 or newer.

## Install and test

    python -m pip install -e .
    python -m unittest discover -s tests

## Quick start

    import asyncio
    from openrobots import CommandPolicy, RobotCommand, RobotHub, SimulatedRobot

    async def main():
        policy = CommandPolicy(
            allowed_commands=frozenset({"stop", "move"}),
            numeric_limits={"speed": 0.25},
        )
        hub = RobotHub(policy)
        robot = SimulatedRobot()
        hub.register("demo", robot)

        await hub.connect("demo")
        result = await hub.execute(
            "demo", RobotCommand("move", {"speed": 0.1})
        )
        print(result)
        await hub.disconnect("demo")

    asyncio.run(main())

## Add a robot integration

Implement the `RobotAdapter` interface (`connect`, `disconnect`,
`get_state`, and `execute`) and register it with `RobotHub`. Keep
vendor-specific transport and command translation inside the adapter.

The default command policy allows only `stop`. Additional commands must be
explicitly enabled. Numeric limits are generic checks, not a substitute
for device-specific safety procedures, hardware interlocks, emergency
stops, testing in a controlled environment, and human supervision.
The included simulator is the only adapter supplied.
""",
    "openrobots/pyproject.toml": """\
[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[project]
name = "openrobots-framework"
version = "0.1.0"
description = "An extensible, simulator-first framework for multiple robot types"
readme = "README.md"
requires-python = ">=3.11"
license = { text = "MIT" }
dependencies = []

[tool.setuptools.packages.find]
where = ["src"]
""",
    "openrobots/.gitignore": """\
__pycache__/
*.py[cod]
*.egg-info/
.venv/
build/
dist/
""",
    "openrobots/src/openrobots/__init__.py": """\
\"\"\"OpenRobots: a simulator-first multi-robot framework.\"\"\"

from .core import CommandPolicy, RobotAdapter, RobotCommand, RobotHub
from .simulator import SimulatedRobot

__all__ = [
    "CommandPolicy",
    "RobotAdapter",
    "RobotCommand",
    "RobotHub",
    "SimulatedRobot",
]
""",
    "openrobots/src/openrobots/core.py": """\
\"\"\"Shared interfaces and policy checks for robot adapters.\"\"\"

from __future__ import annotations

from dataclasses import dataclass, field
import math
from typing import Any, Mapping, Protocol


@dataclass(frozen=True)
class RobotCommand:
    \"\"\"A normalized command for a robot-specific adapter.\"\"\"

    name: str
    parameters: Mapping[str, Any] = field(default_factory=dict)


class RobotAdapter(Protocol):
    \"\"\"Interface implemented by each robot-specific integration.\"\"\"

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def get_state(self) -> Mapping[str, Any]: ...

    async def execute(self, command: RobotCommand) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class CommandPolicy:
    \"\"\"Allow commands explicitly and cap selected numeric parameters.

    The default permits only the universal ``stop`` command. Choose
    parameter limits for the target robot and its units.
    \"\"\"

    allowed_commands: frozenset[str] = frozenset({"stop"})
    numeric_limits: Mapping[str, float] = field(default_factory=dict)

    def validate(self, command: RobotCommand) -> None:
        if command.name not in self.allowed_commands:
            raise PermissionError(
                f"Command {command.name!r} is not allowed by policy"
            )

        for key, limit in self.numeric_limits.items():
            value = command.parameters.get(key)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ValueError(f"Parameter {key!r} must be a number")
            if not math.isfinite(value) or abs(value) > limit:
                raise ValueError(
                    f"Parameter {key!r} exceeds its configured limit"
                )


class RobotHub:
    \"\"\"Manage adapters behind a shared command-policy boundary.\"\"\"

    def __init__(self, policy: CommandPolicy | None = None) -> None:
        self._policy = policy or CommandPolicy()
        self._robots: dict[str, RobotAdapter] = {}

    def register(self, robot_id: str, adapter: RobotAdapter) -> None:
        if not robot_id:
            raise ValueError("robot_id must not be empty")
        if robot_id in self._robots:
            raise ValueError(f"Robot {robot_id!r} is already registered")
        self._robots[robot_id] = adapter

    def _get(self, robot_id: str) -> RobotAdapter:
        try:
            return self._robots[robot_id]
        except KeyError as exc:
            raise KeyError(f"Unknown robot: {robot_id}") from exc

    async def connect(self, robot_id: str) -> None:
        await self._get(robot_id).connect()

    async def disconnect(self, robot_id: str) -> None:
        await self._get(robot_id).disconnect()

    async def get_state(self, robot_id: str) -> Mapping[str, Any]:
        return await self._get(robot_id).get_state()

    async def execute(
        self, robot_id: str, command: RobotCommand
    ) -> Mapping[str, Any]:
        self._policy.validate(command)
        return await self._get(robot_id).execute(command)
""",
    "openrobots/src/openrobots/simulator.py": """\
\"\"\"A harmless in-memory adapter for development and tests.\"\"\"

from __future__ import annotations

from typing import Any, Mapping

from .core import RobotCommand


class SimulatedRobot:
    \"\"\"Record commands in memory without controlling physical hardware.\"\"\"

    def __init__(self) -> None:
        self.connected = False
        self.last_command: str | None = None

    async def connect(self) -> None:
        self.connected = True

    async def disconnect(self) -> None:
        self.connected = False

    async def get_state(self) -> Mapping[str, Any]:
        return {
            "connected": self.connected,
            "last_command": self.last_command,
        }

    async def execute(self, command: RobotCommand) -> Mapping[str, Any]:
        if not self.connected:
            raise RuntimeError("Connect the simulator before sending commands")
        self.last_command = command.name
        return await self.get_state()
""",
    "openrobots/tests/test_openrobots.py": """\
import unittest

from openrobots import CommandPolicy, RobotCommand, RobotHub, SimulatedRobot


class OpenRobotsTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.robot = SimulatedRobot()
        self.hub = RobotHub(
            CommandPolicy(
                allowed_commands=frozenset({"stop", "move"}),
                numeric_limits={"speed": 0.25},
            )
        )
        self.hub.register("demo", self.robot)
        await self.hub.connect("demo")

    async def test_simulator_records_allowed_command(self):
        state = await self.hub.execute(
            "demo", RobotCommand("move", {"speed": 0.1})
        )
        self.assertEqual(state["last_command"], "move")

    async def test_policy_rejects_unlisted_command(self):
        with self.assertRaises(PermissionError):
            await self.hub.execute("demo", RobotCommand("launch"))

    async def test_policy_rejects_out_of_range_value(self):
        with self.assertRaises(ValueError):
            await self.hub.execute(
                "demo", RobotCommand("move", {"speed": 1.0})
            )

    async def test_simulator_requires_connection(self):
        await self.hub.disconnect("demo")
        with self.assertRaises(RuntimeError):
            await self.hub.execute("demo", RobotCommand("stop"))


if __name__ == "__main__":
    unittest.main()
""",
}


def main() -> None:
    archive = Path("openrobots.zip")
    with ZipFile(archive, "w", ZIP_DEFLATED) as zip_file:
        for name, content in FILES.items():
            zip_file.writestr(name, content)
    print(f"Created {archive.resolve()}")


if __name__ == "__main__":
    main()