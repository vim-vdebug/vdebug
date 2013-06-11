require 'rspec/core/rake_task'

namespace :test do
  desc "Run all tests (unit and integration/specs)"
  task :all do
    puts "Running unit tests"
    Rake::Task["test:unit"].execute
    puts "Runing integration (spec) tests"
    Rake::Task[:spec].execute
  end

  desc "Run unit tests"
  task :unit do
    cmd = "python vdebugtests.py"
    puts cmd
    system cmd
  end

  desc "Run integration tests (alias for `spec`)"
  task :integration do
    Rake::Task[:spec]
  end
end

RSpec::Core::RakeTask.new(:spec)

task :default => :spec

