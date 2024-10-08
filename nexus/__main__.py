import argparse
import logging
import os.path
import signal
import sys

from getpass import getpass
import vinput

from nexus import __doc__, __version__
from nexus.Freqlog import Freqlog
from nexus.Freqlog.Definitions import Age, BanlistAttr, CaseSensitivity, ChordMetadata, ChordMetadataAttr, Defaults, \
    Order, WordMetadata, WordMetadataAttr
from nexus.GUI import GUI
from nexus.Version import Version


def main():
    """
    nexus CLI
    Exit codes:
        0: Success (including graceful keyboard interrupt during startlog) / word is not banned
        1: Forceful keyboard interrupt during startlog / checkword result contains a banned word
        2: Invalid command or argument
        3: Invalid value for argument
        4: Could not access database
        5: Requested word or chord not found
        6: Tried to ban already banned word or unban already unbanned word
        7: ValueError during merge db (likely requirements not met)
        8: Upgrade cancelled
        9: Keyboard interrupt during startup banlist password input
        11: Python version < 3.11
        100: Feature not yet implemented
    """
    # Error and exit on Python version < 3.11
    if sys.version_info < (3, 11):
        print("Python 3.11 or higher is required")
        sys.exit(11)

    log_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "NONE"]

    # Common arguments
    # Log and path must be SUPPRESS for placement before and after command to work
    #   (see https://stackoverflow.com/a/62906328/9206488)
    log_arg = argparse.ArgumentParser(add_help=False)
    log_arg.add_argument("-l", "--log-level", default=argparse.SUPPRESS, help=f"One of {log_levels}",
                         metavar="level", choices=log_levels)
    path_arg = argparse.ArgumentParser(add_help=False)
    path_arg.add_argument("--freqlog-db-path", default=argparse.SUPPRESS, help="Path to db backend to use")
    case_arg = argparse.ArgumentParser(add_help=False)
    case_arg.add_argument("-c", "--case", default=CaseSensitivity.INSENSITIVE.name, help="Case sensitivity",
                          choices={case.name for case in CaseSensitivity})
    num_arg = argparse.ArgumentParser(add_help=False)
    num_arg.add_argument("-n", "--num", type=int, required=False,
                         help=f"Number of words to return (0 for all), default {Defaults.DEFAULT_NUM_WORDS_CLI}")
    search_arg = argparse.ArgumentParser(add_help=False)
    search_arg.add_argument("-f", "--find", metavar="search", dest="search", help="Search for (part of) a word",
                            required=False)
    upgrade_arg = argparse.ArgumentParser(add_help=False)
    upgrade_arg.add_argument("--upgrade", action="store_true", help="Upgrade database if necessary")

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description=__doc__, epilog="Made with love by CharaChorder, source code, license, and more info available at "
                                    "https://github.com/CharaChorder/nexus")
    parser.add_argument("-l", "--log-level", default="INFO", help=f"One of {log_levels}",
                        metavar="level", choices=log_levels)
    parser.add_argument("--freqlog-db-path", default=Defaults.DEFAULT_DB_PATH, help="Path to db backend to use")
    subparsers = parser.add_subparsers(dest="command", title="Commands")

    # Start freqlogging
    parser_start = subparsers.add_parser("startlog", help="Start logging", parents=[log_arg, path_arg, upgrade_arg])
    parser_start.add_argument("--new-word-threshold", default=Defaults.DEFAULT_NEW_WORD_THRESHOLD, type=float,
                              help="Time in seconds after which character input is considered a new word")
    parser_start.add_argument("--chord-char-threshold", default=Defaults.DEFAULT_CHORD_CHAR_THRESHOLD, type=int,
                              help="Time in milliseconds between characters in a chord to be considered a chord")
    parser_start.add_argument("--allowed-chars", default=Defaults.DEFAULT_ALLOWED_CHARS,
                              help="Chars to be considered as part of words")
    parser_start.add_argument("--allowed-first-chars",
                              default=Defaults.DEFAULT_ALLOWED_FIRST_CHARS,
                              help="Chars to be considered as the first char in words")
    parser_start.add_argument("--modifier-keys", default=Defaults.DEFAULT_MODIFIERS,
                              help="Specify which modifier keys to use",
                              choices=Defaults.MODIFIER_NAMES,
                              nargs='+')
    # Num words
    subparsers.add_parser("numwords", help="Get number of words in freqlog",
                          parents=[log_arg, path_arg, case_arg, upgrade_arg])

    # Get words
    parser_words = subparsers.add_parser("words", help="Get list of freqlogged words",
                                         parents=[log_arg, path_arg, case_arg, num_arg, search_arg, upgrade_arg])
    parser_words.add_argument("word", help="Word(s) to get data of", nargs="*")
    parser_words.add_argument("-e", "--export", help="Export all freqlogged words as csv to file"
                                                     "(ignores word args)", required=False)
    parser_words.add_argument("-s", "--sort-by", default=WordMetadataAttr.frequency.name,
                              help=f"Sort by (default: {WordMetadataAttr.frequency.name})",
                              choices=[attr.name for attr in WordMetadataAttr])
    parser_words.add_argument("-o", "--order", default=Order.DESCENDING, help="Order (default: DESCENDING)",
                              choices=[order.name for order in Order])

    # Get chords
    parser_chords = subparsers.add_parser("chords", help="Get list of stored freqlogged chords",
                                          parents=[log_arg, path_arg, num_arg, upgrade_arg])
    parser_chords.add_argument("chord", help="Chord(s) to get data of", nargs="*")
    parser_chords.add_argument("-e", "--export", help="Export freqlogged chords as csv to file"
                                                      "(ignores chord args)", required=False)
    parser_chords.add_argument("-s", "--sort-by", default=ChordMetadataAttr.frequency.name,
                               help=f"Sort by (default: {ChordMetadataAttr.frequency.name})",
                               choices=[attr.name for attr in ChordMetadataAttr])
    parser_chords.add_argument("-o", "--order", default=Order.ASCENDING, help="Order (default: DESCENDING)",
                               choices=[order.name for order in Order])

    # Get banned words
    parser_banned = subparsers.add_parser("banlist", help="Get list of banned words",
                                          parents=[log_arg, path_arg, num_arg, upgrade_arg])
    parser_banned.add_argument("-s", "--sort-by", default=BanlistAttr.date_added.name,
                               help="Sort by (default: DATE_ADDED)",
                               choices=[attr.name for attr in BanlistAttr])
    parser_banned.add_argument("-o", "--order", default=Order.DESCENDING, help="Order (default: DESCENDING)",
                               choices=[order.name for order in Order])

    # Check ban
    parser_check = subparsers.add_parser("checkword", help="Check if a word is banned",
                                         parents=[log_arg, path_arg, upgrade_arg])
    parser_check.add_argument("word", help="Word(s) to check", nargs="+")

    # Ban
    parser_ban = subparsers.add_parser("banword", parents=[log_arg, path_arg, upgrade_arg],
                                       help="Ban a word from being freqlogged and delete any existing entries of it")
    parser_ban.add_argument("word", help="Word(s) to ban", nargs="+")

    # Unban
    parser_unban = subparsers.add_parser("unbanword", help="Unban a word from being freqlogged",
                                         parents=[log_arg, path_arg, upgrade_arg])
    parser_unban.add_argument("word", help="Word(s) to unban", nargs="+")

    # Delete word
    parser_delete = subparsers.add_parser("delword", help="Delete a word from freqlog",
                                          parents=[log_arg, path_arg, case_arg, upgrade_arg])
    parser_delete.add_argument("word", help="Word(s) to delete", nargs="+")

    # Delete logged chord
    parser_delete = subparsers.add_parser("delchordentry", help="Delete a chord entry from freqlog",
                                          parents=[log_arg, path_arg, upgrade_arg])
    parser_delete.add_argument("chord", help="Chord entry/ies to delete", nargs="+")

    # Stop freqlogging
    # subparsers.add_parser("stoplog", help="Stop logging", parents=[log_arg])

    # Version
    parser.add_argument("-v", "--version", action="version", version=f"%(prog)s {__version__}")

    # Merge db
    parser_merge = subparsers.add_parser("mergedb", help="Merge two Freqlog databases", parents=[log_arg, upgrade_arg])
    parser_merge.add_argument("--ban-data-keep", default=Age.OLDER.name,
                              help=f"Which ban data to keep (default: {Age.OLDER.name})",
                              choices=[age.name for age in Age])
    parser_merge.add_argument("src1", help="Path to first source database")
    parser_merge.add_argument("src2", help="Path to second source database")
    parser_merge.add_argument("dst", help="Path to destination database")

    # Parse arguments
    args = parser.parse_args()

    # Set up console logging
    if args.log_level == "NONE":
        logging.disable(logging.CRITICAL)
    else:
        logging.basicConfig(level=args.log_level, format="%(asctime)s - %(message)s")
    logging.debug(f"Args: {args}")

    exit_code = 0

    # Check for updates
    outdated, latest_version = Version.fetch_latest_nexus_version()
    if outdated is True:
        # TODO: Update automatically if the current version is outdated
        if latest_version is None:
            logging.warning("Update check failed, there may be a new version of nexus available. The latest version "
                            "can be found at https://github.com/CharaChorder/nexus/releases/latest")
        else:
            logging.info(f"Version {latest_version} of nexus is available! (You are running v{__version__}) "
                         "The latest version can be found at https://github.com/CharaChorder/nexus/releases/latest")

    # Show GUI if no command is given
    if not args.command:
        try:
            sys.exit(GUI(args).exec())
        except Exception as e:
            logging.error(e)
            sys.exit(8)

    # CLI upgrade
    # DB path not manually specified and DB exists in current directory and no file is at default path
    if (args.freqlog_db_path == Defaults.DEFAULT_DB_PATH and Freqlog.is_backend_initialized(Defaults.DEFAULT_DB_FILE)
            and not os.path.isfile(Defaults.DEFAULT_DB_PATH)):
        choice = ""
        if not args.upgrade:
            print(f"[Upgrade]: Freqlog now defaults to '{Defaults.DEFAULT_DB_PATH}' for database location. "
                  f"Move your database from the current directory ({os.getcwd()})? [Y/n]:", end=" ")
            try:
                choice = input().lower()
            except KeyboardInterrupt:
                print()
                logging.error("DB move cancelled")
                sys.exit(8)
        if choice != "n":
            try:
                os.rename(Defaults.DEFAULT_DB_FILE, Defaults.DEFAULT_DB_PATH)
            except OSError as e:
                logging.error(e)
                sys.exit(8)

    # Validate arguments before creating Freqlog object
    match args.command:
        case "startlog":
            try:  # Validate backend
                Freqlog.is_backend_initialized(args.freqlog_db_path)
            except (ValueError, PermissionError, IsADirectoryError) as e:
                logging.error(e)
                exit_code = 4
            if args.new_word_threshold <= 0:
                logging.error("New word threshold must be greater than 0")
                exit_code = 3
            if args.chord_char_threshold <= 0:
                logging.error("Chord character threshold must be greater than 0")
                exit_code = 3
            if len(args.allowed_chars) == 0:
                logging.error("Must allow at least one char")
                exit_code = 3
            if len(args.allowed_first_chars) == 0:
                logging.error("Must allow at least one first char")
                exit_code = 3
            if args.allowed_first_chars - args.allowed_chars:
                logging.error("Allowed first chars must be a subset of allowed chars")
                exit_code = 3
        case "words":
            if args.num and args.num < 0:
                logging.error("Number of words must be >= 0")
                exit_code = 3
        case "chords":
            if args.num and args.num < 0:
                logging.error("Number of chords must be >= 0")
                exit_code = 3
        case "banlist":
            if args.num and args.num < 0:
                logging.error("Number of words must be >= 0")
                exit_code = 3

    def _prompt_for_upgrade(db_version: Version) -> None:
        """Prompt user to upgrade"""
        nonlocal args
        logging.warning(
            f"You are running version {__version__} of nexus, but your database is on version {db_version}.")
        if not args.upgrade:
            print("Backup your database before upgrading!!! Upgrade? [y/N]:", end=" ")
            try:
                choice = input().lower()
            except KeyboardInterrupt:
                print()  # clear the input line
                logging.error("Upgrade cancelled")
                sys.exit(8)
            if choice != "y":
                logging.error("Upgrade cancelled")
                sys.exit(8)

    def _prompt_for_password(new: bool, desc: str = "") -> str:
        """
        Prompt user for password
        :param new: Whether this is a new password
        :param desc: Description of database (optional)
        """
        try:
            if desc:
                desc += " "
            if new:
                while True:
                    password = getpass(f"Choose a new password to encrypt your {desc}banlist with: ")
                    if len(password) < 8:
                        logging.warning("Password should be at least 8 characters long.")
                        if input(f"Continue without securely encrypting your {desc}banlist? [y/N]: ").lower() != "y":
                            continue
                    if getpass(f"Confirm {desc}banlist password: ") == password:
                        return password
                    logging.error("Passwords don't match")
            else:
                return getpass(f"Enter your {desc}banlist password: ")
        except KeyboardInterrupt:
            sys.exit(9)

    # Parse commands
    if args.command == "mergedb":  # Merge databases
        logging.warning("This feature has yet to be thoroughly tested and is not guaranteed to work. Manually verify"
                        f"(via an export) that the destination DB ({args.dst}) contains all your data after merging.")
        try:  # Get passwords
            input("DANGER: Backup your databases before merging!!! Press enter to continue.")
            src1_pass = _prompt_for_password(False, "source database 1")
            src2_pass = _prompt_for_password(False, "source database 2")
            dst_pass = _prompt_for_password(True, "destination database")
        except KeyboardInterrupt:
            logging.error("Merge cancelled")
            sys.exit(8)
        try:
            src1 = Freqlog(args.src1, lambda _: src1_pass, loggable=False, upgrade_callback=_prompt_for_upgrade)
            src1.merge_backends(args.src2, args.dst, Age[args.ban_data_keep], lambda _: src2_pass, lambda _: dst_pass)
            sys.exit(0)
        except Exception as e:
            logging.error(e)
            exit_code = 7

    if args.command == "stoplog":  # Stop freqlogging
        # Kill freqlogging process
        logging.warning("This feature hasn't been implemented." +
                        "To stop freqlogging gracefully, simply kill the process (Ctrl-c)")
        exit_code = 100
        # TODO: implement

    # Exit before creating Freqlog object if checks failed
    if exit_code != 0:
        sys.exit(exit_code)

    # All following commands require a freqlog object (except startlog)
    freqlog: Freqlog | None = None
    if args.command != "startlog":
        try:
            freqlog = Freqlog(args.freqlog_db_path, password_callback=_prompt_for_password, loggable=False,
                              upgrade_callback=_prompt_for_upgrade)
        except Exception as e:
            logging.error(e)
            sys.exit(4)

    if args.command == "numwords":  # Get number of words
        print(f"{freqlog.num_words(CaseSensitivity[args.case])} words in freqlog")
        sys.exit(0)

    # All following commands use a num argument
    try:
        num = args.num if args.num else Defaults.DEFAULT_NUM_WORDS_CLI
    except AttributeError:
        num = Defaults.DEFAULT_NUM_WORDS_CLI

    match args.command:
        case "startlog":  # Start freqlogging
            try:
                freqlog = Freqlog(args.freqlog_db_path, password_callback=_prompt_for_password, loggable=True)
            except Exception as e:
                logging.error(e)
                sys.exit(4)
            mods = vinput.KeyboardModifiers()
            logging.debug('Activated modifier keys:')
            for mod in args.modifier_keys:
                logging.debug(' - ' + str(mod))
                setattr(mods, mod, True)
            signal.signal(signal.SIGINT, lambda _: freqlog.stop_logging())
            freqlog.start_logging(args.new_word_threshold, args.chord_char_threshold, args.allowed_chars,
                                  args.allowed_first_chars, mods)
        case "checkword":  # Check if word is banned
            for word in args.word:
                if freqlog.check_banned(word):
                    print(f"'{word}' is banned")
                    exit_code = 1
                else:
                    print(f"'{word}' is not banned")
        case "banword":  # Ban word
            for word in args.word:
                if not freqlog.ban_word(word):
                    exit_code = 6
        case "unbanword":  # Unban word
            for word in args.word:
                if not freqlog.unban_word(word):
                    exit_code = 6
        case "delword":  # Delete word
            for word in args.word:
                if not freqlog.delete_word(word, CaseSensitivity[args.case]):
                    print(f"Word '{word}' not found")
                    exit_code = 5
        case "delchordentry":  # Delete chord entry
            logging.debug("args.chord: " + str(args.chord))
            for chord in args.chord:
                if not freqlog.delete_logged_chord(chord):
                    print(f"Chord '{chord}' not found")
                    exit_code = 5
        case "words":  # Get words
            if args.export:  # Export words
                freqlog.export_words_to_csv(args.export, num, WordMetadataAttr[args.sort_by],
                                            args.order == Order.DESCENDING, CaseSensitivity[args.case])
            elif len(args.word) == 0:  # All words
                res = freqlog.list_words(limit=num, sort_by=WordMetadataAttr[args.sort_by],
                                         reverse=args.order == Order.DESCENDING,
                                         case=CaseSensitivity[args.case], search=args.search if args.search else "")
                if len(res) == 0:
                    print("No words in freqlog. Start typing!")
                else:
                    for word in res:
                        print(word)  # TODO: pretty print
            else:  # Specific words
                if num:
                    logging.warning("-n/--num argument ignored when specific words are given")
                words: list[WordMetadata] = []
                for word in args.word:
                    res = freqlog.get_word_metadata(word, CaseSensitivity[args.case])
                    if res is None:
                        print(f"Word '{word}' not found")
                        exit_code = 5
                    else:
                        words.append(res)
                if len(words) > 0:
                    for word in sorted(words, key=lambda x: getattr(x, args.sort_by),
                                       reverse=(args.order == Order.DESCENDING)):
                        print(word)
        case "chords":  # Get chords
            if args.export:  # Export chords
                freqlog.export_chords_to_csv(args.export, num, ChordMetadataAttr[args.sort_by],
                                             args.order == Order.DESCENDING)
            elif len(args.chord) == 0:  # All chords
                res = freqlog.list_logged_chords(num, ChordMetadataAttr[args.sort_by],
                                                 args.order == Order.DESCENDING)
                if len(res) == 0:
                    print("No chords in freqlog. Start chording!")
                else:
                    for chord in res:
                        print(chord)
            else:  # Specific chords
                if num:
                    logging.warning("-n/--num argument ignored when specific chords are given")
                chords: list[ChordMetadata] = []
                for chord in args.chord:
                    res = freqlog.get_chord_metadata(chord)
                    if res is None:
                        print(f"Chord '{chord}' not found")
                        exit_code = 5
                    else:
                        chords.append(res)
                if len(chords) > 0:
                    for chord in sorted(chords, key=lambda x: getattr(x, args.sort_by),
                                        reverse=(args.order == Order.DESCENDING)):
                        print(chord)
        case "banlist":  # Get banned words
            banlist = freqlog.list_banned_words(limit=num, sort_by=BanlistAttr[args.sort_by],
                                                reverse=args.order == Order.DESCENDING)
            if len(banlist) == 0:
                print("No banned words")
            else:
                print("Banned words:")
                for entry in banlist:
                    print(entry)
    sys.exit(exit_code)


if __name__ == '__main__':
    main()
