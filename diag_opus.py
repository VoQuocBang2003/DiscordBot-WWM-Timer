import discord, os
p = os.path.join(os.getcwd(), 'libopus-0.dll')
print('path', p, 'exists', os.path.exists(p))
print('before', discord.opus.is_loaded())
try:
    discord.opus.load_opus(p)
    print('loaded from', p)
except Exception as e:
    print('load error', type(e).__name__, e)
print('after', discord.opus.is_loaded())
