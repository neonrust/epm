# epm

Command-line TV episode calendar/manager/scheduler/tracker (EPisode Manager)

## Dependencies

- requests [https://pypi.org/project/requests]

It also uses themoviedb.org for information lookup. An API key is required.

## Configuration

All cache and configuration is stored in:

    ~/.config/epm/series
	
## TMDb API key

Key is read from the environment:

    TMDB_API_KEY

## Usage

NOTE: this is not up to date :(

    epm / Episode Manager / (c)2021 André Jonsson
    Version 0.4 (2021-11-16) 
    Usage: epm [<options>] [.<command> [<args>]]
    
    Where <command> is:
       .add     Add series
               <title> [<year>]
               <IMDb ID>
       .unseen  Show unseen episodes of series
               #/<IMDb ID>                     (show only specific)
               [<pattern>]                     (show only matching)
               --future                        (also unreleased, max 1)
       .list    List configured series
               --all                           (include also archived series)
               --archived                      (list only archived series)
               [<pattern>]                     (show only matching)
       .mark    Mark episode as seen
               #/<IMDb ID> <season> <episode>  (specific episodes)
               #/<IMDb ID> <season>            (whole seasons)
               #/<IMDb ID>                     (the whole series)
       .unmark  Remove mark, as added by mark
               #/<IMDb ID> <season> <episode>  (single episode)
               #/<IMDb ID> <season>            (a whole season)
               #/<IMDb ID>                     (the whole series)
       .delete  Delete series (completely remove from config)
               #/<IMDb ID>
       .archive Archive series (still in config, but not normally shown)
               #/<IMDb ID>
       .restore Restore previously archived series
               #/<IMDb ID>
       .refresh Refresh episode data (forcibly)
               [#/<IMDb ID>]                    (only specified series)
               [<pattern>]                      (only matching series)
    
    Remarks:
      # = Series number, as listed by e.g. the list or unseen commands.
      Marking/unmarking also supports ranges, e.g. epm mark 1 2 1-10
      If the given command is not found, it is used as a pattern to the unseen command.
      Only "shortest unique" part of the commands is required, e.g. ".ar"  for "archive".


## Examples

NOTE: this is not up to date :(


Add a series you'd like to monitor.

    > epm .add twin peaks 
    Found 10 series:
       #1 Twin Peaks                             1990-1991
       #2 Twin Peaks                             2017-    
       #3 Twin                                   2019-    
       #4 Georgia Coffee: Twin Peaks             1993-    
       #5 Twin Turbos                            2018-2020
       #6 Twin Hawks                             1984-1985
       #7 Twin of Brothers                       2004-    
       #8 Lexi & Lottie: Trusty Twin Detectives  2016-2017
       #9 Twin Hearts                            2003-2004
      #10 Twin My Heart                          2019-    
    Select series (1 - 10) to add --> 1    [user input]
    Series added:  (series renumbered)
       #1 Twin Peaks  1990-1991  tt0098936

Now the series is added.

All added series can be listed by using the `list` / `ls` command:

    > epm .ls
       #1 Twin Peaks              1990-1991  tt0098936
           Total: Unseen: 30  1d 53min
           Next: s1e01 Pilot  

Mark episodes that has been watched:

    > epm .mark 1 s1
    Marked 8 episodes as seen:  7h
       [edit]list of episodes cut out[/edit]
	> epm .mark 1 s2e1-20
    Marked 20 episodes as seen:  16h 17min
       [edit]list of episodes cut out[/edit]

Then, show current status, using no arguments (or the `unseen` command):

    > epm
       #1 Twin Peaks             1990-1991   1 episode
        Next: s2e21 Episode #2.21              
