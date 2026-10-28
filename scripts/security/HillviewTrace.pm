# Test-only instrumentation, loaded through PERL5OPT in a disposable container.
package HillviewTrace;
use strict;
use warnings;
use Image::ExifTool;
use Image::ExifTool::GM;
sub record {
    open my $fh, '>>', $ENV{HILLVIEW_TRACE_FILE} or die $!;
    print $fh join("\t", @_), "\n";
    close $fh;
}
INIT {
    no warnings 'redefine';
    my $original = \&Image::ExifTool::ProcessDirectory;
    *Image::ExifTool::ProcessDirectory = sub ($$$;$) {
        my ($et, $dir, $table) = @_;
        record('directory', $table->{TABLE_NAME} || 'unknown',
            'PrintConv=' . ($et->Options('PrintConv') || 0),
            'ExtractEmbedded=' . ($et->Options('ExtractEmbedded') || 0));
        goto &$original;
    };
    my $gm = \&Image::ExifTool::GM::Process_mrld;
    my $wrapped = sub ($$$) { record('GM_DICTIONARY'); goto &$gm; };
    *Image::ExifTool::GM::Process_mrld = $wrapped;
    $Image::ExifTool::GM::mrld{PROCESS_PROC} = $wrapped;
}
1;
