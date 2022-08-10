
_00 = '\x1b[m'     # normal (reset all)
_0 = '\x1b[22;23;24;39m' # normal FG style
_0B = '\x1b[49m'  # normal BG color
_b = '\x1b[1m'     # bold
_f = '\x1b[2m'     # faint
_i = '\x1b[3m'     # italic
_fi = '\x1b[2;3m'  # faint & italic
_u = '\x1b[4m'     # underline
_g = '\x1b[32;1m'  # good/green
_c = '\x1b[33;1m'  # command
_o = '\x1b[34;1m'  # option
_K = '\x1b[K'      # clear end-of-line
_E = '\x1b[41;97;1m' # ERROR (white on red)
_EOL = '\x1b[666C' # move far enough to the right to hit the edge
_S = '\x1b[s'      # save cursor position
_L = '\x1b[u'      # load/restore saved cursor position
