#!/usr/bin/perl

use strict;
use Term::ReadLine;
use Term::ReadPassword;
use Net::FTPSSL;

my $SIMULATE;
if (@ARGV == 1 && $ARGV[0] eq "--simulate") {
    $SIMULATE = 1;
    print STDERR "Waring: Simulating FTP sessions!\n";
}
elsif (@ARGV > 0) {
    die "usage: image-upload [--simulate]\n";
}
my ($a, $b);
my %servers = ("andonyar.com" => {host => "andonyar.com", pathprefix => "/"});
my $current_server;
my $ftp;

my $term = Term::ReadLine->new('Simple Perl calc');

my $ERR_INCONS = 0;
my $ERR_ERROR = 1;
my $ERR_FATAL = 2;
my %errors_count = ($ERR_INCONS => 0, $ERR_ERROR => 0, $ERR_FATAL => 0);

# Development hints:
# Use &err($ERR_FATAL, ...) when the process should die and the error
# originates from an FTP problem. (&err dies in this case.)
# Use die if it is a bug in this program.
# Use &err with another error code when processing contiues.

sub err {
    my ($type, $path, $command, $filename, $description) = @_;
    my %typenames = ($ERR_INCONS => "Inconsistency", $ERR_ERROR => "Error", $ERR_FATAL => "Fatal");
    print STDERR "$typenames{$type}: `$command $filename` in $path" .  ($description ? ": $description" : "") . "\n";
    $errors_count{$type} += 1;
    if ($type == $ERR_FATAL) { die; }
}

sub ask {
    my $toplevel = $_[0];
    my $info = $servers{$toplevel}; # Updating information in place
    $info->{"host"} ||= $term->readline("host name for $toplevel: ");
    $info->{"pathprefix"} ||= $term->readline("path prefix for $toplevel (must end in /): ");
    $info->{"username"} ||= $term->readline("user name for $toplevel: ");
    $info->{"password"} ||= read_password("password for $toplevel: ");
}

sub open_ftp {
    my $toplevel = $_[0];
    $current_server = $servers{$toplevel};
    unless ($current_server->{'host'} && $current_server->{'username'} && $current_server->{'password'} && $current_server->{'pathprefix'}) {
        die "Not enough information for toplevel directory $toplevel\n";
    }
    if ($SIMULATE) {
        $ftp = FakeFTPSSL->new($current_server->{'host'},
                               Encryption => EXP_CRYPT,
                               Debug => 1);
    }
    else {
        $ftp = Net::FTPSSL->new($current_server->{'host'},
                                Encryption => EXP_CRYPT,
                                Debug => 1);
    }
    $ftp->login($current_server->{'username'}, $current_server->{'password'})
        or die "Can't login: ", $ftp->last_message();
    $ftp->binary() or die "Call to binary failed.";
}

sub close_ftp {
    $ftp->quit();
    $current_server = undef;
}

sub open_blob {
    my $blob = $_[0];
    my $GIT;
    die "$blob is not a blob" unless `git cat-file -t $blob` eq "blob\n";
    my $child_pid = open($GIT, "-|")   // die "can't fork: $!";
    if (!$child_pid) {
        exec("git", "cat-file", "blob", $blob);
    }
    return $GIT;
}

sub close_blob {
    my $GIT = $_[0];
    close $GIT or die (($! ? "error closing pipe ($!) for " :
                             "git returned with status $? for ") .
                      join(" ", @_));
}

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

sub ls {
    # Makes a list of trees in a and in b: (trees of a, trees of b)
    my $tree = $_[0];
        
    my $ls = &git_call("git", "ls-tree", "-z", $tree);

    my @list;
    while ($ls =~ /\G\d*(\d{3}) (\w+) (\w+)\t([^\x00]+)\x00/sg) {
        push @list, {
            mode => $1,
            type => $2,
            object => $3,
            filename => $4,
        };
    }

    return @list;
}

sub put {
    my ($blob, $filename) = @_;
    my $data = &open_blob($blob);
    $ftp->put($data, $filename);
    &close_blob($data);
}

sub del {
    my $filename = $_[0];
    $ftp->delete($filename);
}

sub chmod {
    my ($filename, $mode) = @_;
    $ftp->quot("chmod", $mode, $filename);
}

sub assert_cwd {
    my $should = "$current_server->{'pathprefix'}$_[0]";
    my $is = $ftp->pwd();
    unless ($should eq $is) {
        die "Working directory not in sync (should be $should but is $is)\n" unless $should eq $is;
    }
}

sub rput {
    #recursive put
    #$tree must be from the new revision, of course
    my ($tree, $path, $filename) = @_;

    $ftp->mkdir($filename) or &err($ERR_INCONS, $path, "mkdir", $filename, "rput: directory already exists");
    unless ($ftp->cwd($filename)) {
        &err($ERR_ERROR, $path, "cwd", $filename, "rput: failed, but directory has been created previouls, skipping");
        &assert_cwd($path);
        return;
    }

    my @list = &ls($tree);
    for (@list) {
        if ($_->{'type'} eq "blob") {
            &put($_->{'object'}, $_->{'filename'});
        }
        elsif ($_->{'type'} eq "tree") {
            &rput($_->{'object'}, "$path/$filename", $_->{'filename'});
        }
        else {
            die "rput encountered unsupported git object type $_->{'type'}";
        }
    }

    $ftp->cdup() or &err($ERR_FATAL, $path, "cdup", $filename);
}

sub rdel {
    #recursive delete
    #$tree must be from the old revision, of course
    my ($tree, $path, $filename) = @_;

    unless ($ftp->cwd($filename)) {
        &err($ERR_INCONS, $path, "cwd", $filename, "rdel: directory to be removed seems not to exist");
        &assert_cwd($path);
        return;
    }

    my @list = &ls($tree);
    for (@list) {
        if ($_->{'type'} eq "blob") {
            &del($_->{'filename'});
        }
        elsif ($_->{'type'} eq "tree") {
            &rdel($_->{'object'}, "$path/$filename", $_->{'filename'});
        }
        else {
            die "rdel encountered unsupported git object type $_->{'type'}";
        }
    }

    $ftp->cdup() or &err($ERR_FATAL, $path, "cdup", $filename);
    $ftp->rmdir($filename) or &err($ERR_INCONS, $path, "rmdir", $filename, "rdel: directory not empty");
}


my %actions = (
    put => sub { &put($_[0], $_[2]) },
    del => sub { &put($_[2]) },
    rput => \&rput,
    rdel => \&rdel,
    chmod => sub { &chmod($_[0], $_[2]) },
);

my $revision_line = <STDIN>;
$revision_line =~ /^([^\s]+) ([^\s]+)$/ or die "Malformed first line\n";
$a = $1;
$b = $2;
print STDERR "$a -> $b\n";
<STDIN> eq "\n" or die "Malformed second line\n";

while (<STDIN>) {
    chop;
    last unless $_;
    &ask($_);
}    

while (my $line = <STDIN>) {
    chop $line;
    if ($line =~ m~^((put|rdel|rput|chmod) (\w+)|(del)) ([^/]+)/(.*?)([^/]+)$~) {
        my ($cmd, $object, $toplevel, $path, $filename) = ($2 || $4, $3, $5, $6, $7);
        chop $path; # Remove / at end
        $toplevel =~ s/\\x\{(d+)\}/chr($1)/ge;
        $filename =~ s/\\x\{(d+)\}/chr($1)/ge;
        #in case of chmod, $object stores the mode
        if (!defined $current_server) {
            # No server connection present, open
            &open_ftp($toplevel);
        }
        $ftp->cwd("$current_server->{'pathprefix'}$path") 
            or &err($ERR_FATAL, "", "cwd", "$current_server->{'pathprefix'}$path");
        unless (exists $actions{$cmd}) {
            &err($ERR_FATAL, "", "", "", "Command $cmd unknown");
        }
        &{$actions{$cmd}}($object, $path, $filename);
    }
    elsif ($line) {
        &err($ERR_ERROR, "", "", "", "I don't undestand this command: $line");
    }
    else {
        # Empty line, close server.
        &close_ftp if $current_server;
    }
}
&close_ftp if $current_server;

if (keys %errors_count) {
    print "Encountered $errors_count{$ERR_INCONS} consistency errors\n" .
          "and $errors_count{$ERR_ERROR} normal errors.\n";
}
else {
    print "No erros encountered. Have a nice day.\n"
}


package FakeFTPSSL;

sub new {
    print STDERR "FTPSSL: Creating server with " . join(", ", @_) . "\n";
    my $self = { wd => '/' };
    bless($self);           # but see below
    return $self;
}

sub login {
    my $self = shift;
    print STDERR "FTPSSL: login " . join(" ", @_) . "\n";
    return 1;
}

sub binary {
    my $self = shift;
    print STDERR "FTPSSL: binary\n";
    return 1;
}

sub mkdir {
    my $self = shift;
    print STDERR "FTPSSL: mkdir " . join(" ", @_) . "\n";
    return 1;
}

sub rmdir {
    my $self = shift;
    print STDERR "FTPSSL: rmdir " . join(" ", @_) . "\n";
    return 1;
}

sub delete {
    my $self = shift;
    print STDERR "FTPSSL: delete " . join(" ", @_) . "\n";
    return 1;
}

sub put {
    my $self = shift;
    print STDERR "FTPSSL: put " . join(" ", @_) . "\n";
    my $fh = shift;
    my $linecount = 0;
    while (<$fh>) { ++$linecount }
    print STDERR "FTPSSL: received $linecount lines.\n";
    return 1;
}

sub quot {
    my $self = shift;
    print STDERR "FTPSSL: quot " . join(" ", @_) . "\n";
    return 1;
}

sub cwd {
    my $self = shift;
    if ($_[0] =~ m|^/|) {
        $self->{'wd'} = $_[0];
    }
    else {
        $self->{'wd'} .= "/$_[0]";
    }
    print STDERR "FTPSSL: chwd " . join(" ", @_) . 
        "; New working directory: $self->{'wd'}\n";
    return 1;
}

sub cdup {
    my $self = shift;
    $self->{'wd'} =~ m|^(.*)/[^/]+$|s;
    $self->{'wd'} = $1;
    print STDERR "FTPSSL: cdup; New working directory: $self->{'wd'}\n";
    return 1;
}

sub pwd {
    my $self = shift;
    print STDERR "FTPSSL: pwd; Answer: $self->{'wd'}\n";
    return $self->{'wd'};
}

sub quit {
    my $self = shift;
    print STDERR "FTPSSL: quit " . join(" ", @_) . "\n";
    return 1;
}

