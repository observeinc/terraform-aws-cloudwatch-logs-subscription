resource "local_file" "this" {
  content = templatefile("subscribelogs.yaml.template", {
     code = indent(10, file("../lambda/index.py"))
  })
  filename = "${path.module}/generated/subscribelogs.yaml"
}