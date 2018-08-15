require 'rspec/core/rake_task'
require 'cucumber'
require 'cucumber/rake/task'

namespace :test do
  desc "Run all tests (unit and integration/specs)"
  task :all do
    puts "Running unit tests"
    Rake::Task["test:unit"].execute
    puts "Running integration (spec) tests"
    Rake::Task[:spec].execute
    puts "Running cucumber features"
    Rake::Task[:features].execute
  end

  desc "Run unit tests"
  task :unit do
    if ENV["COVERAGE"]
      puts "Running unit tests with coverage (view output at ./htmlcov/index.html)"
      cmd = "coverage run -m unittest discover && coverage report -m --include='python3/vdebug/*'"
    else
      cmd = "python -m unittest discover"
    end
    puts cmd
    system cmd
  end

  desc "Run integration tests (alias for `spec`)"
  task :integration do
    Rake::Task[:spec]
  end
end

RSpec::Core::RakeTask.new(:spec)
Cucumber::Rake::Task.new(:features) do |t|
  t.cucumber_opts = "features --format pretty"
end

task :default => "test:all"
