import arr_scripts as a

print([x for x in dir(a) if not x.startswith(chr(95))])
