#!/usr/bin/perl

use strict;

my ($a, $b) = @ARGV;
die "Usage: image-diff old_revision new_revision" unless $a && $b;
my %ignore_toplevel_dirs = ();

sub git_call {
    my $GIT;
    my $child_pid = open($GIT, "-|")   // die "can't fork: $!";
    if (!$child_pid) {
        exec(@_);
    }
    my $data = join("", <$GIT>);
    close $GIT or die (($! ? "error closing pipe ($!) for " :
                            "git returned with status $? for ") .
                      join(" ", @_));
    return $data;
}

sub diff {
    # Creates and parses a `git diff-tree $a:$_[0] $b:$_[0]`
    my $diff = &git_call("git", "diff-tree", "-z", "$a:$_[0]", "$b:$_[0]");

    my @changes;
    while ($diff =~ /\G:(\d+) (\d+) (\w+) (\w+) (?|([ADMTUX])()\x00([^\x00]+)()|([CR])(\d*)\x00([^\x00]+)\x00([^\x00]+))\x00/sg) {
        push @changes, {
            src_mode => $1,
            dst_mode => $2,
            src_sha1 => $3,
            dst_sha1 => $4,
            status => $5,
            score => $6,
            src_filename => $7,
            dst_filename => $8,
            filename => $7 # For convenience in case of ADMTUX
        };
    }

    return @changes;
}

sub is_tree {
    my $object = $_[0];

    my $type = &git_call("git", "cat-file", "-t", $object);

    chomp $type;
    return ($type eq "tree");
}

sub encode {
    my $string = $_[0];
    $string =~ s/([^\w\/.])/'\x{'.ord($1).'}'/ge;
    return $string;
}

sub add {
    my ($path, $change) = @_;
    my $filename = $change->{'filename'};
    if (&is_tree("$b:$path/$filename")) {
        print("rput $change->{'dst_sha1'} ".&encode("$path/$filename")."\n");
    }
    else {
        print("put $change->{'dst_sha1'} ".&encode("$path/$filename")."\n");
    }
}

sub delete {
    my ($path, $change) = @_;
    my $filename = $change->{'filename'};
    if (&is_tree("$a:$path/$filename")) {
        print("rdel $change->{'src_sha1'} ".&encode("$path/$filename")."\n");
    }
    else {
        print("del ".&encode("$path/$filename")."\n");
    }
}

sub modify {
    my ($path, $change) = @_;
    my $filename = $change->{'filename'};
    if (&is_tree("$a:$path/$filename")) {
        die "Modify must not be called for a directory!";
    }
    print("put $change->{'dst_sha1'} ".&encode("$path/$filename")."\n");
}

sub changetype {
    my ($path, $change) = @_;
    my $filename = $change->{'filename'};
    # We simply remove the old file and add the new one.
    &delete(@_);
    &add(@_);
}

sub copy {
    my ($path, $change) = @_;
    # Note that we could have a score, so this need not be an exact
    # copy. Therefore delete and put
    &delecte(@_);
    &add(@_);
}

sub rename {
    # Note that we could have a score, so this need not be an exact
    # copy. Therefore delete and put
    &delecte(@_);
    &add(@_);
}

sub diff_error {
    my ($rev, $path, $change) = @_;
    # This is a problem severe enough to die, because we are either in
    # an unmerged stage or git has a bug.
    die "Invalid change encountered: " . join " ", @$change;
}

my %actions = (
    A => \&add,
    D => \&delete,
    M => \&modify,
    T => \&changetype,
    U => \&diff_error,
    X => \&diff_error,
    C => \&copy,
    R => \&rename,
);

sub changed_toplevel {
    # Determines which top level files have changed
    # (Maybe doesn't do what it should.)
    my @changes = &diff("");
    @changes = grep { $_->{'status'} =~ /A|M|T|C|R/  } @changes;
    @changes = grep { &is_tree("$b:" . ($_->{"dst_filename"} || $_->{"src_filename"})) } @changes;
    return map { $_->{"dst_filename"} || $_->{"src_filename"} } @changes;
}

sub process {
    my $path = $_[0];
    my @changes = &diff($path);
    for (@changes) {
        if ($_->{'status'} eq 'M' and &is_tree("$a:$path/$_->{'filename'}")) {
            &process("$path/$_->{'filename'}");
        }
        else {
            &{$actions{$_->{'status'}}}($path, $_);
        }
    }
}

my @toplevel = grep { !$ignore_toplevel_dirs{$_} } &changed_toplevel;

print "$a $b\n\n";

for (@toplevel) {
    print(&encode($_)."\n");
}

for (@toplevel) {
    print "\n";
    &process($_);
}

print("\n");


