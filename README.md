# epm

Commandline-based episode calendar/manager/scheduler/tracker (EPisode Manager)

Inspired by [Episode Calendar](https://episodecalendar.com).


## Concepts

Series that have been added to epm can have one of these user states:

- `planned`  Just added, nothing seen.
- `started`  At least one episode seen, but not all.
- `completed` All episodes seen but not archived (or explicitly restored).
- `archived`  All episodes seen and series is "ended" or "cancelled". 
- `abandoned` Archived, but not all episodes seen.

Transitions between these states are implicit and automatic. 
However, the `archived` (or `abandoned`) state can be manually controlled by the `archive` command, and undone with the `restore` command.

How a series moves between the states is hopefully quite obvious when using the tool.

A few notable transitions:

- Command `mark`: If the last episode of a series was marked (and it's ended/cancelled), it moves to `archived` state.
- Command `unmark`: If in `archived` state, it moves to `started`. If no episode marked at all afterwards, it moves to `planned` state.


## Dependencies

Requires Python 3.9 (type hints are used, the lower-case variants).

- [requests](https://pypi.org/project/requests)
- [API key for The Movie Database](https://www.themoviedb.org)
- [orjson](https://pypi.org/project/orjson) (highly recommended, but optional)
- `zstd` command-line tool. For compressing backups. (optional)

<img alt="TMDb" src="https://www.themoviedb.org/assets/2/v4/logos/v2/blue_short-8e7b30f73a4020692ccca9c88bafe5dcb6f8a62a4c6bc55cd9ba82bb2cd95f6c.svg" width="30%">


## File locations

EPM's data and configuration is located in:

    ~/.config/episode_manager/

Mainly the database file `series` (and its backups).
If this data is important to you, backing up this directory is highly recommended.

Run-time configuration is stored in the file `config`.

Arguably, the database file should be under ~/.local/share but I preferred to keep it all in one place.


## TMDb API key

To use EPM, an API key is required. Apply for this here: https://developer.themoviedb.org.
Since EPM is open-source and its source is literally open on the client (being written in Python), it's not possible to use a shared key.

Key is read from the environment:

    TMDB_API_KEY

Or set it in the configuration:

    epm config --api-key <your key>


## Examples

Note, the exact appearance of these output examples might not be accurate.
They're continuously being tweaked and improved.


Add a series you'd like to monitor:

    ⯈epm add twin peaks 
    Found 10 series:
    >  #1 Twin Peaks                             1990-1991  <
       #2 Twin Peaks                             2017-    
       #3 Twin                                   2019-    
       #4 Georgia Coffee: Twin Peaks             1993-    
       #5 Twin Turbos                            2018-2020
       #6 Twin Hawks                             1984-1985
       #7 Twin of Brothers                       2004-    
       #8 Lexi & Lottie: Trusty Twin Detectives  2016-2017
       #9 Twin Hearts                            2003-2004
      #10 Twin My Heart                          2019-    
    
    <series selected in interactive menu>
    
    Series added:
        1 Twin Peaks  1990-1991  tt0098936

Now the series is added.

All added series can be listed by using the `list` / `ls` command:

    ⯈epm ls
        1 Twin Peaks              1990-1991  tt0098936
           Total: Unseen: 30  1d 53min
           Next:  1:01 Pilot  

Mark episodes that has been watched:

    ⯈epm mark 1
    Marked 8 episodes as seen:  7h
       <list of episodes cut out>

	⯈epm mark 1 s2e1-20
    Marked 20 episodes as seen:  16h 17min
       <list of episodes cut out>

Then, show current status, using no arguments (or the `unseen` command):

    ⯈epm
        1 Twin Peaks  (1990-1991)   1 unseen
           Next:   2:22 Episode #2.22                      46min 1991-06-10

For a bit more "fancy" display of future episodes, use the `calendar` command, e.g.:

    ⯈epm cal 2
    ┏━━━━━━━━━━━━┥ August 2022  week 31
    ┃  1st Monday
    ┃  2nd Tuesday
    ┃  3rd Wednesday
    ┃  4th Thursday
    ┃      • The Orville   3:10 Future Unknown                                                          
    ┃      • For All Mankind   3:09 Coming Home                       46min
    ┃  5th Friday
    ┃  6th Saturday
    ┃  7th Sunday
    ┃      • Westworld   4:07 Metanoia                                52min
    ┠──────── week 32
    ┃  8th Monday
    ┃  9th Tuesday
    ┃ 10th Wednesday
    ┃ 11st Thursday
    ┃      • For All Mankind   3:10 Han                                                                 
    ┃ 12nd Friday
    ┃ 13rd Saturday
    ┃ 14th Sunday
    ┃      • Westworld   4:08 Que Será, Será                          59min


Sadly, these examples doesn't show that all output from epm is colorized
for clarity and emphasis.

But here's a screenshot of the menu shown by the `search` command (very similar to `add`):

![search](screenshots/search.png)

Basically the difference when using the `add` command is that the bottom text `... to exit` 
then says `RET to add   ESC to exit`. 


## Usage

    epm / Episode Manager / (c)2022 André Jonsson
    Version 0.9 (2022-08-01)
    Usage: epm [<command>] [<args ...>]
    
    Where <command> is:  (one-letter alias highlighted)
    search      Search for a series.
    add         Search for a series and (optionally) add it.
    delete      Completely remove a series - permanently!
    show        Show/list series
    calendar    Show episode releases by date
    unseen      Show unseen episodes of series
    mark        Mark a series, season or specific episode as seen.
    unMark      Unmark a series/season/episode - reverse of mark command.
    Archive     Archving series - hides from normal list command.
    Restore     Restore series - reverse of archive command.
    refresh     Refresh episode data of all non-archived series.
    config      Configure.
    help        Shows this help page.
    (none)  ▶  unseen
    
    See: epm <command> --help for command-specific help.
    
    Remarks:
    # = Series listing number, e.g. as listed by the list command.
    If an argument does not match a command, it will be used as argument to the default command.
    Shortest unique prefix of a command is enough, e.g. "ar"  for "archive".
    Install 'orjson' for faster load/save
    Using zstd to compress database backups.
