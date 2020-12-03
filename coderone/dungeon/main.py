#!/usr/bin/env python
"""
 Dungeons & Data Structures
 Coder One AI game tournament challenge
"""

import argparse
import os
import time
import sys
import logging
import json
from contextlib import ExitStack
from typing import Dict, List, Tuple, Union, NamedTuple, Any, Optional

from appdirs import user_config_dir

from .game_recorder import FileRecorder, Recorder
# from coderone.dungeon.agent_driver.simple_driver import Driver
from .agent_driver.multiproc_driver import Driver

from .game import Game
from .arcade_client import GameWindow, WIDTH, HEIGHT, PADDING


APP_NAME = 'coderone.dungeon'

ASSET_DIRECTORY = os.path.join(os.path.dirname(__file__), 'assets')
DEFAULT_CONFIG_FILE = 'config.json'

print(f"!!!! {ASSET_DIRECTORY}")


SCREEN_TITLE = "Coder Oone: Dungeons & Data Structures"
# Do the math to figure out our screen dimensions
SCREEN_WIDTH =  PADDING[0]*2 + WIDTH * 12
SCREEN_HEIGHT = PADDING[1]*3 + HEIGHT * 10


TICK_STEP = 0.1 		# Number of seconds per 1 iteration of game loop
ITERATION_LIMIT = 3*60*10 	# Max number of iteration the game should go on for, None for unlimited

logger = logging.getLogger()
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
# logger.setLevel(logging.DEBUG)


def __load_or_generate_config(config_file:Optional[str]) -> dict:
	## Setting up the players using the config file

	if config_file:
		# A custom config file location given:
		try:
			with open(config_file) as f:
				config_data = json.load(f)
		except: # Failed to load config, fallback to default values
			logger.error(f"config file '{config_file}' not found, using default value")
			raise
	else:
		# Default config file expected:
		config_dir = user_config_dir(APP_NAME)
		config_file = os.path.join(config_dir, DEFAULT_CONFIG_FILE)

		try:
			with open(config_file) as f:
				config_data = json.load(f)
		except FileNotFoundError: # Failed to load config, fallback to default values
			logger.warning(f"No default config file found, generating...")
			config_data = {
				"headless": False,
				"interactive": False,
				"start_paused": True,
				"wait_end": 5,
				"max_iterations": ITERATION_LIMIT,
				"tick_step": TICK_STEP
			}

			os.makedirs(config_dir, exist_ok=True)
			with open(config_file, "w") as f:
				json.dump(config_data, f, indent=4, sort_keys=True)
		
	
	config_data.setdefault('start_paused', False)
	config_data.setdefault('wait_end', 10)
	config_data.setdefault('assets', ASSET_DIRECTORY)
	config_data.setdefault('interactive', False)
	config_data.setdefault('update_time_step', TICK_STEP)
	config_data.setdefault('no_text', False)  # A work around Pillow (Python image library) bug	

	return config_data


# Borrowed from flask!
def _prepare_import(path):
    """Given a filename this will try to calculate the python path, add it
    to the search path and return the actual module name that is expected.
    """
    path = os.path.realpath(path)

    fname, ext = os.path.splitext(path)
    if ext == ".py":
        path = fname

    if os.path.basename(path) == "__init__":
        path = os.path.dirname(path)

    module_name = []

    # move up until outside package structure (no __init__.py)
    while True:
        path, name = os.path.split(path)
        module_name.append(name)

        if not os.path.exists(os.path.join(path, "__init__.py")):
            break

    if sys.path[0] != path:
        sys.path.insert(0, path)

    return ".".join(module_name[::-1])


def __load_agent_drivers(cntx: ExitStack, agent_modules, config:dict, watch=False):
	agents = []
	n_agents = len(agent_modules)

	logger.info(f"Loading agent modules: {n_agents} required")
	for counter, agent_module in enumerate(agent_modules):
		try:
			logger.info(f"[{counter + 1}/{n_agents}] loading agent driver: {agent_module}")
			module_name = _prepare_import(agent_module)
			driver = Driver(module_name, watch, config)
			cntx.enter_context(driver)
			agents.append(driver)
		except Exception as e:
			logger.error(f"failed to load agent module {agent_module}")
			logger.error(e, exc_info=True)
			return None
	
	return agents


def run(agent_modules, headless=False, watch=False, interactive=False, config=None, recorder=None):
	# Create a new game
	row_count = config.get('rows', Game.ROW_COUNT)
	column_count = config.get('columns', Game.COLUMN_COUNT)
	iteration_limit = config.get('max_iterations', ITERATION_LIMIT)
	is_interactive = interactive or config.get('interactive')

	# Load agent modules
	with ExitStack() as stack:
		agents = __load_agent_drivers(stack, agent_modules, watch=watch, config=config)
		if not agents:
			sys.exit(1)  # Exiting with an error, no contest

		game = Game(row_count=row_count, column_count=column_count, max_iterations=iteration_limit, recorder=recorder)

		# Add all agents to the game
		for agent_driver in agents:
			game.add_agent(agent_driver.agent(), agent_driver.name)

		# Add a player for the user if running in interactive mode or configured interactive
		user_pid = game.add_player("Player") if is_interactive else None

		game.generate_map()

		tick_step = config.get('tick_step')
		if headless or config.get('headless'):
			while not game.game_ended:
				logger.info(f"Game step [{game.tick_counter}/{game.max_iterations}]... ")

				cycle_start_time = time.time()
				game.tick(tick_step)
				dt = time.time() - cycle_start_time

				stats = game.stats()
				for p in stats['players'].values():
					name = "{}{}".format(p['name'], '(bot)' if p['is_bot'] else "")
					logger.info(f"{name} HP: {p['hp']} / Ammo: {p['ammo']} / Score: {p['score']}, loc: ({p['position'][0]}, {p['position'][0]})")

				logger.debug(f"...step [{game.tick_counter}/{game.max_iterations}] completed in {dt*1000.0:.4f}ms")

				sleep_time = tick_step - dt
				if sleep_time > 0:
					logger.debug(f"has time to sleep for {sleep_time}sec")
					time.sleep(sleep_time)

		else:
			window = GameWindow(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, game, user_pid, config, intractive=is_interactive)
			window.run(tick_step)

		# Announce game winner and exit
		results = game.stats()
		print(json.dumps(results, indent=4, sort_keys=True))

	# We done here, all good.
	sys.exit(0)


def main():
	parser = argparse.ArgumentParser(description=SCREEN_TITLE)
	
	parser.add_argument('--headless', action='store_true',
					default=False,
					help='run without graphics')
	parser.add_argument('--interactive', action='store_true',
					default=False,
					help='all a user to contol a player')
	parser.add_argument('--watch', action='store_true',
					default=False,
					help='automatically reload agents on file changes')
	parser.add_argument('--record', type=str,
					help='file name to record game')
	parser.add_argument('--config', type=str,
					default=None,
					help='path to the custom config file')

	parser.add_argument("agents", nargs="+", help="agent module")

	args = parser.parse_args()

	config = __load_or_generate_config(args.config)

	if args.headless and len(args.agents) < 2:
		print("At least 2 agents must be provided in the match mode. Exiting", file=sys.stderr)
		sys.exit(1)

	recorder = FileRecorder(args.record) if args.record else Recorder()

	# Everything seems in order - lets start the game
	with recorder:
		run(args.agents, config=config, headless=args.headless, watch=args.watch, interactive=args.interactive, recorder=recorder)


if __name__ == "__main__":
	main()