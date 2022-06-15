with open('subscribelogs.yaml.template') as f:
    template_str = f.read()

with open('../lambda/index.py') as f:
    code_str = f.read()

code_lines = code_str.split('\n')
code_lines_padded = [' ' * 10 + line for line in code_lines]
code_str_padded = '\n'.join(code_lines_padded)
yaml_str = template_str.replace('{{ .CODE }}', code_str_padded)

with open('subscribelogs.yaml', 'w') as f:
    f.write(yaml_str)
