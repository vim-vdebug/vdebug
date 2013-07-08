Given "I have a file $file containing" do |file, content|
  File.open file, "w" do |f|
    f.write content
  end
end
