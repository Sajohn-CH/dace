import astunparse
import unittest
from dace.frontend.python.newast import GlobalResolver
from dace.frontend.python import astutils


def test():
    a = 5
    if a == 5:
        b = 7
        f(a, b)
    else:
        b = 0
        g(b, a + 5)

    return b


class TestGlobalResolver(unittest.TestCase):
    def test_simple(self):
        test_ast, _, _, _ = astutils.function_to_ast(test)
        code = astunparse.unparse(
            GlobalResolver({
                'b': 9,
                'a': -4
            }).visit(test_ast))
        self.assertTrue('return 9' in code)
        self.assertTrue('f(a, b)' in code)
        self.assertTrue('g(b' in code)


if __name__ == '__main__':
    unittest.main()
