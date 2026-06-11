"""AntiRaidVerify cog package."""

from .antiraidverify import AntiRaidVerify


async def setup(bot):
    await bot.add_cog(AntiRaidVerify(bot))
