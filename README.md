# epm

Command-line TV episode calendar/manager/scheduler/tracker (EPisode Manager)

Requires python 3.9, because type hints are used (the lower-case variants).

## Dependencies

- requests [https://pypi.org/project/requests]

It also uses themoviedb.org for information lookup. An API key is required.

## Configuration

All cache and configuration is stored in:

    ~/.config/epm/series
	
## TMDb API key

Key is read from the environment:

    TMDB_API_KEY

## Examples

Add a series you'd like to monitor.

    > epm add twin peaks 
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

    > epm ls
       #1 Twin Peaks              1990-1991  tt0098936
           Total: Unseen: 30  1d 53min
           Next: s1e01 Pilot  

Mark episodes that has been watched:

    > epm mark 1 s1
    Marked 8 episodes as seen:  7h
       [edit]list of episodes cut out[/edit]
	> epm mark 1 s2e1-20
    Marked 20 episodes as seen:  16h 17min
       [edit]list of episodes cut out[/edit]

Then, show current status, using no arguments (or the `unseen` command):

    > epm
       #1 Twin Peaks             1990-1991   1 episode
        Next: s2e21 Episode #2.21              
## Usage

    epm / Episode Manager / (c)2021 André Jonsson
    Version 0.5 (2022-07-02) 
    Usage: epm [<options>] [mode] [<args>]]
    
    Where <mode> is:
       add       Add series
       delete    Delete series (completely remove from config)
       unseen    Show unseen episodes of series
       list      List series
       mark      Mark episode as seen
       unMark    Remove mark, as added by m
       Archive   Archive series (still in config, but not normally shown)
       Restore   Restore previously archived series
       refresh   Refresh episode data (forcibly)
       help     Show this help information
    
    Also try: <mode> --help
    
    Remarks:
      # = Series number, as listed by e.g. the lisr or unmark modes.
      If an argument does not match a command, it will be used as an argument to the unseen command.
      Only "shortest unique" part of the commands is required, e.g. ".ar"  for "archive".
   

