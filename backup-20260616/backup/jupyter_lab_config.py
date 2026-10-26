c.ServerApp.allow_root = True
c.ServerApp.ip = '0.0.0.0'
c.ServerApp.port = 8888
c.PasswordIdentityProvider.hashed_password = 'argon2:$argon2id$v=19$m=10240,t=10,p=8$n7WqLc6CUyz6EiSkDYEyow$dJUORO3ziiVCjgKDvId1ww1tSOuJqRJJXn2CVWhXUO8'
c.ServerApp.open_browser = False
c.ServerApp.allow_origin = '*'
c.ServerApp.disable_check_xsrf = True
