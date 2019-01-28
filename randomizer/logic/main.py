# Main randomizer logic module that the front end calls.

import hashlib
import random
import re

from randomizer import data
from . import bosses
from . import characters
from . import enemies
from . import flags
from . import items
from . import keys
from . import map
from . import spells
from . import utils
from .patch import Patch

# Current version number
VERSION = '8.0.0beta4'


class Settings:
    def __init__(self, mode, debug_mode=False, custom_flags=None):
        """
        :type mode: str
        :type debug_mode: bool
        :type custom_flags: dict
        """
        self._mode = mode
        self._debug_mode = debug_mode
        self._custom_flags = {}
        if custom_flags is not None:
            self._custom_flags.update(custom_flags)

    @property
    def mode(self):
        """:rtype: str"""
        return self._mode

    @property
    def debug_mode(self):
        """:rtype: bool"""
        return self._debug_mode

    @property
    def flag_string(self):
        """
        Returns:
            str: Computed flag string for these settings.
        """
        flag_strings = []

        for category in flags.CATEGORIES:
            for flag in category.flags:
                if self.is_flag_enabled(flag):
                    # Solo flag that begins with a dash.
                    if flag.value.startswith('-'):
                        flag_strings.append(flag.value)
                    # Flag that may have a subsection of choices and/or options.
                    else:
                        chars = []

                        choice = self.get_flag_choice(flag)
                        if choice:
                            chars.append(choice.value[1:])

                        for option in flag.options:
                            if self.is_flag_enabled(option):
                                chars.append(option.value[1:])

                        # If flag begins with @, it doesn't do anything on its own.  Must have some option enabled.
                        if flag.value.startswith('@'):
                            if chars:
                                flag_strings.append(flag.value[1:] + ''.join(chars))
                        else:
                            flag_strings.append(flag.value[:1] + ''.join(chars))

        return ' '.join(flag_strings)

    def is_flag_enabled(self, flag):
        """
        Args:
            flag(randomizer.logic.flags.Flag):

        Returns:
            bool: True if flag is enabled, False otherwise.
        """
        return bool(self._custom_flags.get(flag.value))

    def get_flag_choice(self, flag):
        """
        Args:
            flag(randomizer.logic.flags.Flag):

        Returns:
            randomizer.logic.flags.Flag: Selected choice for this flag.
        """
        val = self._custom_flags.get('{0}-choice'.format(flag.value))
        for choice in flag.choices:
            if choice.value == val:
                return choice
        return None


class GameWorld:
    """Master container class representing the entire game world to be randomized.  This class doesn't do much on its
    own, but it holds all the data being randomized so the actual logic can look at and change different things across
    a single instance of the world.
    """

    def __init__(self, seed, settings):
        """
        :type seed: int
        :type settings: randomizer.logic.main.Settings
        """
        self.seed = seed
        self.settings = settings
        self.file_select_character = 'Mario'
        self.file_select_hash = 'MARIO1 / MARIO2 / MARIO3 / MARIO4'
        self._rebuild_hash()

        # *** Get vanilla data for randomizing.
        # Characters
        self.characters = data.characters.get_default_characters(self)
        self.character_join_order = self.characters[:]
        self.levelup_xps = data.characters.LevelUpExps()

        # Spells
        self.spells = data.spells.get_default_spells(self)
        self.spells_dict = dict([(s.index, s) for s in self.spells])

        # Starting FP.
        self.starting_fp = data.spells.STARTING_FP

        # Items
        self.items = data.items.get_default_items(self)
        self.items_dict = dict([(i.index, i) for i in self.items])

        # Shops
        self.shops = data.items.get_default_shops(self)

        # Enemies
        self.enemies = data.enemies.get_default_enemies(self)
        self.enemies_dict = dict([(e.index, e) for e in self.enemies])

        # Get enemy attack data.
        self.enemy_attacks = data.attacks.get_default_enemy_attacks(self)

        # Get enemy formation data.
        self.enemy_formations, self.formation_packs = data.formations.get_default_enemy_formations(self)
        self.enemy_formations_dict = dict((f.index, f) for f in self.enemy_formations)
        self.formation_packs_dict = dict((p.index, p) for p in self.formation_packs)

        # Get key item data.
        self.key_locations = data.keys.get_default_key_item_locations()

        # Get boss location data.
        self.boss_locations = data.bosses.get_default_boss_locations()

    @property
    def open_mode(self):
        """Check if this game world is Open mode.

        Returns:
            bool:

        """
        return self.settings.mode == 'open'

    @property
    def debug_mode(self):
        """Get debug mode flag.

        Returns:
            bool:

        """
        return self.settings.debug_mode

    def get_item_instance(self, cls):
        """
        Args:
            cls: Item class to get this world's instance of.

        Returns:
            randomizer.logic.data.items.Item: Item instance for this world.
        """
        return self.items_dict[cls.index]

    def get_enemy_instance(self, cls):
        """
        Args:
            cls: Enemy class to get this world's instance of.

        Returns:
            randomizer.logic.data.enemies.Enemy: Enemy instance for this world.
        """
        return self.enemies_dict[cls.index]

    def get_enemy_formation_by_index(self, index):
        """
        :type index: int
        :rtype: randomizer.logic.enemies.EnemyFormation
        """
        return self.enemy_formations_dict[index]

    def get_formation_pack_by_index(self, index):
        """
        :type index: int
        :rtype: randomizer.logic.enemies.FormationPack
        """
        return self.formation_packs_dict[index]

    def randomize(self):
        """Randomize this entire game world instance."""
        # Seed the PRNG at the start.
        random.seed(self.seed)

        characters.randomize_all(self)
        spells.randomize_all(self)
        items.randomize_all(self)
        enemies.randomize_all(self)
        bosses.randomize_all(self)
        keys.randomize_all(self)

        # Rebuild hash after randomization.
        self._rebuild_hash()

    def _rebuild_hash(self):
        """Build hash value for choosing file select character and file name hash.
        Use the same version, seed, mode, and flags used for the database hash.
        """
        final_seed = bytearray()
        final_seed += VERSION.encode('utf-8')
        final_seed += self.seed.to_bytes(4, 'big')
        final_seed += self.settings.mode.encode('utf-8')
        final_seed += self.settings.flag_string.encode('utf-8')
        self.hash = hashlib.md5(final_seed).hexdigest()

    def build_patch(self):
        """Build patch data for this instance.

        :rtype: randomizer.logic.patch.Patch
        """
        patch = Patch()

        # Characters
        for character in self.characters:
            patch += character.get_patch()

        # Update party join script events for the final order.  These are different for standard vs open mode.
        if self.open_mode:
            addresses = [0x1ef86d, 0x1ef86f, 0x1ef871, 0x1fc4f2, 0x1e8b72]
            for addr, character in zip(addresses, self.character_join_order):
                patch.add_data(addr, 0x80 + character.index)
        else:
            # For standard mode, Mario is the first character.  Update the other four only.
            addresses = [0x1e2155, 0x1fc506, 0x1edf98, 0x1e8b79]
            for addr, character in zip(addresses, self.character_join_order[1:]):
                patch.add_data(addr, 0x80 + character.index)

            # Update other battle scripts so Belome eats the first one to join.
            for addr in (
                    0x394b4d,
                    0x394b70,
                    0x394b74,
                    0x394b7d,
                    0x394b7f,
                    0x394b83,
                    0x3ab93f,
                    0x3ab95a,
            ):
                patch.add_data(addr, self.character_join_order[1].index)

        # Learned spells and level-up exp.
        patch += self.levelup_xps.get_patch()

        # Spells
        for spell in self.spells:
            patch += spell.get_patch()

        # Starting FP (twice for starting/max FP)
        patch.add_data(0x3a00dd, utils.ByteField(self.starting_fp).as_bytes() * 2)

        # For debug mode, start with 9999 coins and 99 frog coins.
        if self.debug_mode:
            patch.add_data(0x3a00db, utils.ByteField(9999, num_bytes=2).as_bytes())
            patch.add_data(0x3a00df, utils.ByteField(99, num_bytes=2).as_bytes())

        # Items
        for item in self.items:
            patch += item.get_patch()
        patch += data.items.Item.build_descriptions_patch(self)

        # Shops
        for shop in self.shops:
            patch += shop.get_patch()

        # Enemies
        for enemy in self.enemies:
            patch += enemy.get_patch()
        patch += data.enemies.Enemy.build_psychopath_patch(self)

        # Enemy attacks
        for attack in self.enemy_attacks:
            patch += attack.get_patch()

        # Enemy formations
        for formation in self.enemy_formations:
            patch += formation.get_patch()

        # Open mode specific data.
        if self.open_mode:
            # Key item locations.
            for location in self.key_locations:
                # FIXME
                # print(">>>>>>>> {}".format(location))
                patch += location.get_patch()

            # Boss locations.
            for boss in self.boss_locations:
                # FIXME
                # if boss.has_star:
                #     print(">>>>>>>>>>>>>>>> {}".format(boss.__class__.__name__))
                patch += boss.get_patch()

            # Set flags for seven star mode and Bowser's Keep.
            if self.settings.randomize_stars and self.settings.randomize_stars_seven:
                patch.add_data(0x1fd341, utils.ByteField(0xa2).as_bytes())

            if self.settings.randomize_stars_bk:
                patch.add_data(0x1fd343, utils.ByteField(0xa2).as_bytes())

            # If star piece exp progression is on, set exp values for each star piece number and enable flag.
            if self.settings.randomize_exp_stars:
                patch.add_data(0x39bc44, utils.ByteField(1).as_bytes())  # 0 stars
                patch.add_data(0x39bc46, utils.ByteField(2).as_bytes())  # 1 star
                patch.add_data(0x39bc48, utils.ByteField(3).as_bytes())  # 2 stars
                patch.add_data(0x39bc4a, utils.ByteField(5).as_bytes())  # 3 stars
                patch.add_data(0x39bc4c, utils.ByteField(6).as_bytes())  # 4 stars
                patch.add_data(0x39bc4e, utils.ByteField(7).as_bytes())  # 5 stars
                patch.add_data(0x39bc52, utils.ByteField(11).as_bytes())  # 6/7 stars
                patch.add_data(0x1fd32d, utils.ByteField(0xa0).as_bytes())  # Enable flag

        # Unlock the whole map if in debug mode in standard.
        if self.debug_mode and not self.open_mode:
            patch += map.unlock_world_map()

        # Choose character for the file select screen.
        i = int(self.hash, 16) % 5
        file_select_char_bytes = [0, 7, 13, 25, 19]
        self.file_select_character = [c for c in self.characters if c.index == i][0].__class__.__name__

        # Change file select character graphic, if not Mario.
        if i != 0:
            addresses = [0x34757, 0x3489a, 0x34ee7, 0x340aa, 0x3501e]
            for addr, value in zip(addresses, [0, 1, 0, 0, 1]):
                patch.add_data(addr, file_select_char_bytes[i] + value)

        # Possible names we can use for the hash values on the file select screen.  Needs to be 6 characters or less.
        file_entry_names = {
            'MARIO',
            'MALLOW',
            'GENO',
            'BOWSER',
            'PEACH',
        }
        # Also use enemy names, if they're 6 characters or less.
        for e in self.enemies:
            name = re.sub(r'[^A-Za-z]', '', e.name.upper())
            if len(name) <= 6:
                file_entry_names.add(name)
        file_entry_names = sorted(file_entry_names)

        # Replace file select names with "hash" values for seed verification.
        file_select_names = [
            file_entry_names[int(self.hash[0:8], 16) % len(file_entry_names)],
            file_entry_names[int(self.hash[8:16], 16) % len(file_entry_names)],
            file_entry_names[int(self.hash[16:24], 16) % len(file_entry_names)],
            file_entry_names[int(self.hash[24:32], 16) % len(file_entry_names)],
        ]
        for i, name in enumerate(file_select_names):
            addr = 0x3ef528 + (i * 7)
            val = name.encode().ljust(7, b'\x00')
            patch.add_data(addr, val)

        # Save file select hash text to show the user on the website, but the game uses '}' instead of dash.
        self.file_select_hash = ' / '.join(file_select_names).replace('}', '-')

        # Update ROM title and version.
        title = 'SMRPG-R {}'.format(self.seed).ljust(20)
        if len(title) > 20:
            title = title[:19] + '?'

        # Add title and major version number to SNES header data.
        patch.add_data(0x7fc0, title)
        v = VERSION.split('.')
        patch.add_data(0x7fdb, int(v[0]))

        return patch
