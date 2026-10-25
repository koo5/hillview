#!/usr/bin/env perl
# Benign positive control: reach the advisory's dictionary parser directly.
# This is NOT a JPEG exploit or a claim of reachability from an upload.
use strict;
use warnings;
use Image::ExifTool;
use Image::ExifTool::GM;
my $units = defined $ARGV[0] ? $ARGV[0] : 'unit$marker';
die 'Unsupported control units' if defined $ARGV[0] && $units !~ /\A(?:rpm|kph|widgets\/s)\z/;
my $et = Image::ExifTool->new;
$et->Options(PrintConv => 0);
my $record = "\0" x 448;
substr($record, 0, 4) = pack('N', 1);
substr($record, 12, 64) = pack('Z64', $units);
substr($record, 128, 64) = pack('Z64', 'HillviewProbe');
substr($record, 192, 64) = pack('Z64', 'Harmless trace control');
my $table = Image::ExifTool::GetTagTable('Image::ExifTool::GM::mrld');
Image::ExifTool::GM::Process_mrld($et, { DataPt => \$record, DataPos => 0 }, $table);
my $marl = Image::ExifTool::GetTagTable('Image::ExifTool::GM::marl');
print "Generated PrintConv: ", $marl->{HillviewProbe}{PrintConv}, "\n";
# Do not evaluate the generated expression. The literal marker lets us inspect
# escaping without evaluating attacker-supplied Perl or accessing any secrets.

# Ordinary, explicitly allowlisted controls exercise real print conversion.
# The interpolation-marker control above is never evaluated.
if (defined $ARGV[0]) {
    my $val = 12.5;
    my $formatted = eval $marl->{HillviewProbe}{PrintConv};
    die $@ if $@;
    print "Formatted: ", $formatted, "\n";
}
