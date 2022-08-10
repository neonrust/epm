import re
from typing import Callable

def new(total:int|float, width:int, bar_color:int|str|None=None, bg_color:int|str=4, text_color:str|int|None=None, l_info:Callable|None=None, r_info: Callable|None=None):
	"""
	:param total: Total number of items to process (e.g. 100)
	:param width: Render width
	:param color: Bar color.
	:param bg_color: Bar background color, default: blue.
	:param text_color: Color of text inside bar.
	:param r_info: Function that returns a formatted string for the right-side info text.
	:return: Rendered progress bar string.
	Returns a function that, when called, returns a printable progress bar.
	This function should be kept self-contained (to make it easier to copy, could arguably be a separate package...)
	"""
	#print(f'new_progress: total:{total} width:{width} bg_color:{bg_color} text_color:{text_color} fmt_info:{fmt_info}')

	bar_ch = ('▏', '▎', '▍', '▌', '▋', '▊', '▉')


	def _default_linfo(c, t):
		if not isinstance(c, (int, float)) or t is None:
			return '  ? '
		else:
			percent = int(float(c)/float(t) * 100)
			return '%3.0f%%' % percent

	if l_info is None:
		l_info = _default_linfo

	rinfo_w = len(str(total))
	def _default_rinfo(c, t):
		if not isinstance(c, (int, float)) or t is None:
			c = '?'
			t = '?'
		return f'{c:>{rinfo_w}}/{t:<{rinfo_w}}'

	if r_info is None:
		r_info = _default_rinfo

	CLR = '\x1b[K'   # clear to end-of-line
	INV = '\x1b[7m'  # video inversion
	RST = '\x1b[m'   # reset all attributes
	DIM = '\x1b[2m'  # faint/dim color
	SAVE = '\x1b[s'  # save cursor position
	LOAD = '\x1b[u'  # restore saved cursor position


	bar_0 = ''
	bar_1 = RST
	bar_head = f'\x1b[4{bg_color}m'

	if bar_color is not None:
		bar_0 = f'\x1b[3{bar_color}m'  # will use inversion
		bar_head = bar_0 + bar_head    # no inversion

	text_0 = bar_0
	text_1 = bar_0

	if text_color is not None:
		if bar_color:
			text_0 = f'\x1b[4{text_color};3{bar_color}m'  # w/ inversion
		else:
			text_0 = f'\x1b[4{text_color}m'               # w/ inversion


	def _replace_reps(s, find, repl):
		ptn = re.compile(r'(%s+)' % find)

		def replacer(m):
			count = len(m.group(1))/len(find)
			return repl % { 'n': count, 's': m.group(1) }

		return ptn.sub(replacer, s)

	left_margin = 1  # >= 1
	right_margin = 1 # >= 1

	left_pad = ' '*(left_margin - 1) + '▕'
	right_pad = '▏' + ' '*(right_margin - 1)

	def gen(curr:int|float|str|None, text=None):

		ltotal:int|float|None = total
		lwidth = width

		# if 'curr' is a string, show an "indeterminate" progress bar
		is_indeterminate = isinstance(curr, str)

		if is_indeterminate:
			text = curr
			curr = None
			ltotal = None
		# TODO: show 'spinner' during indeterminate state

		left_info = l_info(curr, ltotal)   # type: ignore
		right_info = r_info(curr, ltotal)  # type: ignore

		linfo_w = 4 + left_margin  # ' 42% '
		lwidth -= linfo_w + right_margin + len(right_info)

		if is_indeterminate:
			bar_w = lwidth
		else:
			completed = curr/ltotal # type: ignore
			bar_w = int(completed*lwidth)  # number of completed segments

		# widths of completed (head) and remaining (tail) segments
		int_w = int(bar_w)
		head = bar_ch[int((bar_w % 1)*len(bar_ch))]
		tail_w = lwidth - int_w - 1

		opt_text = ''
		if text:
			text_done = _replace_reps(text[:int(bar_w)], ' ', '\x1b[%(n)dC')
			text_todo = _replace_reps(text[int(bar_w):], ' ', '\x1b[%(n)dC')

			opt_text = ''
			if text_done:
				opt_text += f'{INV}{text_0}{text_done}{text_1}'
			if text_todo:
				opt_text += f'{RST}{bar_head}{text_todo}'
			if opt_text:
				opt_text += LOAD

		last_bar = ''.join([
				CLR,
				# display 'left info'
				DIM,
				left_info,
				bar_0,
				left_pad,
				SAVE,
				# completed bar segments
				INV,
				' '*int_w,
				bar_1,
				# the "head" segment (single cell, partially completed)
				bar_head, head,
				# remaining bar segments
				(f'%{tail_w}s' % '') if tail_w else '',
				LOAD,
				opt_text,          # ends with LOAD if non-empty
				f'\x1b[{lwidth}C',  # move to right edge
				bar_0, right_pad,
				RST,
				# display 'right info'
				DIM,
				right_info,
				RST,
				])
		#print('BAR:', last_bar.replace('\x1b', 'Σ').replace('\r', 'ΣR').replace('Σ', '\x1b[35;1mΣ\x1b[m'))
		return last_bar

	gen.__name__ = 'progress_bar'
	gen.__doc__ = '''Return a rendered progress bar at 'curr' (of 'total') progress.'''

	setattr(gen, 'total', total)
	setattr(gen, 'width', width)

	return gen
