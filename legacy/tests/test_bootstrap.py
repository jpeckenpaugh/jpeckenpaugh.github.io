import unittest

from app.bootstrap import create_app


class TestBootstrap(unittest.TestCase):
    def test_create_app_sets_combat_actions(self) -> None:
        ctx = create_app()
        self.assertIn("ATTACK", ctx.combat_actions)
        self.assertIn("ATTACK", ctx.offensive_actions)
        self.assertTrue(ctx.router_ctx)
        self.assertTrue(ctx.screen_ctx)


if __name__ == "__main__":
    unittest.main()
