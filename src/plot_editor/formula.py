"""Function-curve column formulas: a small recursive-descent parser.

A Function column plots ``y = f(x)`` (or ``x = g(y)``) typed into its
first data cell. Only simple typed formulas are accepted — digits,
``x``/``y``, ``+ - * / ^ ( ) { }`` and LaTeX-style functions with a
backslash (``\\sin``, ``\\log_2``, ``\\pi`` …). Never ``eval``.
"""

import math
import re
from functools import lru_cache

from .i18n import tr

MAX_FORMULA_CHARS = 500
MAX_FORMULA_DEPTH = 50

_NUM = re.compile(r'(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?')
_NAME = re.compile(r'[A-Za-z]+')
_BSNAME = re.compile(r'\\[A-Za-z]+')
_PREFIX = re.compile(r'([xy])\s*=')

_FUNC1 = {'sin': math.sin, 'cos': math.cos, 'tan': math.tan,
          'arcsin': math.asin, 'arccos': math.acos,
          'arctan': math.atan, 'asin': math.asin, 'acos': math.acos,
          'atan': math.atan, 'sinh': math.sinh, 'cosh': math.cosh,
          'tanh': math.tanh, 'exp': math.exp, 'ln': math.log,
          'lg': math.log10, 'sqrt': math.sqrt, 'abs': abs}
_CONSTS = {'pi': math.pi, 'e': math.e}


class FormulaError(ValueError):
    pass


class Formula:
    """Parsed formula: ``axis`` 'y' means y = f(x) (variable x),
    'x' means x = g(y) (variable y); ``constant`` when no variable."""

    __slots__ = ('axis', 'constant', '_ast')

    def __init__(self, axis, constant, ast):
        self.axis = axis
        self.constant = constant
        self._ast = ast

    def eval(self, v):
        """Value at ``v``; NaN on domain errors or non-real results."""
        try:
            r = _eval(self._ast, float(v))
        except (ValueError, ZeroDivisionError, OverflowError,
                RecursionError):
            return float('nan')
        if isinstance(r, complex):
            return float('nan')
        try:
            r = float(r)
        except (TypeError, ValueError):
            return float('nan')
        return r if math.isfinite(r) else float('nan')


def _eval(node, var):
    k = node[0]
    if k == 'num' or k == 'const':
        return node[1]
    if k == 'var':
        return var
    if k == 'neg':
        return -_eval(node[1], var)
    if k == 'add':
        return _eval(node[1], var) + _eval(node[2], var)
    if k == 'sub':
        return _eval(node[1], var) - _eval(node[2], var)
    if k == 'mul':
        return _eval(node[1], var) * _eval(node[2], var)
    if k == 'div':
        return _eval(node[1], var) / _eval(node[2], var)
    if k == 'pow':
        return _eval(node[1], var) ** _eval(node[2], var)
    # ('call', name, arg, base|None)
    arg = _eval(node[2], var)
    if node[1] == 'log':
        base = 10.0 if node[3] is None else node[3]
        return math.log(arg, base)
    return _FUNC1[node[1]](arg)


def _scan(text):
    toks = []
    i, n = 0, len(text)
    while i < n:
        c = text[i]
        if c.isspace():
            i += 1
            continue
        if c.isdigit() or (c == '.' and i + 1 < n
                           and text[i + 1].isdigit()):
            m = _NUM.match(text, i)
            toks.append(('num', float(m.group()), m.start()))
            i = m.end()
            continue
        if c == '\\':
            m = _BSNAME.match(text, i)
            if m is None:
                raise FormulaError(tr('err_formula_char',
                                      ch=c, pos=i + 1))
            toks.append(('bsname', m.group()[1:], m.start()))
            i = m.end()
            continue
        if c.isalpha():
            m = _NAME.match(text, i)
            toks.append(('name', m.group(), m.start()))
            i = m.end()
            continue
        if text.startswith('**', i):
            toks.append(('op', '**', i))
            i += 2
            continue
        if c in '+-*/^_={}()':
            toks.append(('op', c, i))
            i += 1
            continue
        raise FormulaError(tr('err_formula_char', ch=c, pos=i + 1))
    toks.append(('eof', None, n))
    return toks


class _Parser:
    def __init__(self, text, var):
        self.toks = _scan(text)
        self.i = 0
        self.var = var
        self.depth = 0
        self.has_var = False

    def peek(self):
        return self.toks[self.i]

    def take(self):
        t = self.toks[self.i]
        if t[0] != 'eof':
            self.i += 1
        return t

    def _op(self, *ops):
        t = self.peek()
        return t[0] == 'op' and t[1] in ops

    def _err(self, key, pos=None, **fmt):
        if pos is None:
            pos = self.peek()[2] + 1
        raise FormulaError(tr(key, pos=pos, **fmt))

    def parse(self):
        node = self._expr()
        if self.peek()[0] != 'eof':
            self._err('err_formula_syntax')
        return node

    def _expr(self):
        node = self._term()
        while self._op('+', '-'):
            op = self.take()[1]
            rhs = self._term()
            node = ('add' if op == '+' else 'sub', node, rhs)
        return node

    def _starts_primary(self):
        t = self.peek()
        return t[0] in ('num', 'name', 'bsname') \
            or (t[0] == 'op' and t[1] in ('(', '{'))

    def _term(self):
        node = self._unary()
        while True:
            if self._op('*', '/'):
                op = self.take()[1]
                rhs = self._unary()
                node = ('mul' if op == '*' else 'div', node, rhs)
            elif self._starts_primary():
                # Implicit multiplication: a primary directly
                # following (2x, 2\sin(x), (x+1)(x-1), x\pi).
                node = ('mul', node, self._unary())
            else:
                return node

    def _unary(self):
        neg = False
        while self._op('+', '-'):
            if self.take()[1] == '-':
                neg = not neg
        node = self._power()
        return ('neg', node) if neg else node

    def _power(self):
        base = self._primary()
        if self._op('^', '**'):
            self.take()
            return ('pow', base, self._unary())
        return base

    def _group(self, close):
        self.depth += 1
        if self.depth > MAX_FORMULA_DEPTH:
            self._err('err_formula_deep', max=MAX_FORMULA_DEPTH)
        node = self._expr()
        t = self.take()
        if not (t[0] == 'op' and t[1] == close):
            self._err('err_formula_syntax')
        self.depth -= 1
        return node

    def _primary(self):
        t = self.take()
        if t[0] == 'num':
            return ('num', t[1])
        if t[0] == 'name':
            if t[1] == self.var:
                self.has_var = True
                return ('var',)
            self._err('err_formula_variable', pos=t[2] + 1,
                      var=self.var, name=t[1])
        if t[0] == 'bsname':
            return self._backslash(t)
        if t[0] == 'op' and t[1] in ('(', '{'):
            return self._group(')' if t[1] == '(' else '}')
        self._err('err_formula_syntax', pos=t[2] + 1)

    def _backslash(self, t):
        name = t[1]
        if name in _CONSTS:
            return ('const', _CONSTS[name])
        if name not in _FUNC1 and name != 'log':
            self._err('err_formula_function', pos=t[2] + 1, name=name)
        base = None
        if self._op('_'):
            if name != 'log':
                self._err('err_formula_subscript', pos=t[2] + 1)
            self.take()
            base = self._subscript_base()
        nt = self.peek()
        if not (nt[0] == 'op' and nt[1] in ('(', '{')):
            self._err('err_formula_group', pos=nt[2] + 1, name=name)
        self.take()
        arg = self._group(')' if nt[1] == '(' else '}')
        return ('call', name, arg, base)

    def _subscript_base(self):
        t = self.take()
        if t[0] == 'num':
            v = t[1]
        elif t[0] == 'op' and t[1] == '{':
            self.depth += 1
            if self.depth > MAX_FORMULA_DEPTH:
                self._err('err_formula_deep', max=MAX_FORMULA_DEPTH)
            nt = self.take()
            if nt[0] != 'num':
                self._err('err_formula_syntax', pos=nt[2] + 1)
            v = nt[1]
            ct = self.take()
            if not (ct[0] == 'op' and ct[1] == '}'):
                self._err('err_formula_syntax', pos=ct[2] + 1)
            self.depth -= 1
        else:
            self._err('err_formula_syntax', pos=t[2] + 1)
        if not (math.isfinite(v) and v > 0 and v != 1):
            self._err('err_formula_log_base', pos=t[2] + 1)
        return v


@lru_cache(maxsize=512)
def _compile(text):
    s = text.strip()
    axis = 'y'
    m = _PREFIX.match(s)
    if s.startswith('='):
        s = s[1:].strip()
    elif m is not None:
        axis = m.group(1)
        s = s[m.end():].strip()
    if not s:
        raise FormulaError(tr('err_formula_empty'))
    var = 'x' if axis == 'y' else 'y'
    p = _Parser(s, var)
    ast = p.parse()
    return Formula(axis, not p.has_var, ast)


def parse(text):
    """Parse *text* into a ``Formula``; ``FormulaError`` on bad input."""
    if not isinstance(text, str):
        raise FormulaError(tr('err_formula_empty'))
    if len(text) > MAX_FORMULA_CHARS:
        raise FormulaError(tr('err_formula_too_long',
                              max=MAX_FORMULA_CHARS))
    return _compile(text)


def sample(formula, lo, hi, n=401):
    """``(xs, ys)`` of finite samples of *formula* over ``[lo, hi]``.

    For ``axis == 'x'`` the sampled variable is y: ``xs = g(y)``,
    ``ys`` the y samples. Constant formulas give exactly the two range
    ends; ``lo == hi`` widens by ±0.5.
    """
    lo, hi = float(lo), float(hi)
    if lo == hi:
        lo -= 0.5
        hi += 0.5
    if formula.constant:
        v = formula.eval(0.0)
        if not math.isfinite(v):
            return [], []
        if formula.axis == 'y':
            return [lo, hi], [v, v]
        return [v, v], [lo, hi]
    xs, ys = [], []
    n = max(int(n), 2)
    for i in range(n):
        t = lo + (hi - lo) * i / (n - 1)
        v = formula.eval(t)
        if not math.isfinite(v):
            continue
        if formula.axis == 'y':
            xs.append(t)
            ys.append(v)
        else:
            xs.append(v)
            ys.append(t)
    return xs, ys
