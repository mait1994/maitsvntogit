#!/usr/local/bin/perl

###############################################################################
# Program     : ShowSpectrum.cgi
# Author      : Kerry Deutsch <kdeutsch@systemsbiology.org>
# $Id$
#
# Description : This CGI program displays the requested MSMS (CID) spectrum
#               along with overlaid information about the passed peptide.
#
###############################################################################


###############################################################################
# Basic SBEAMS setup
###############################################################################
use strict;
use lib qw (../../lib/perl);
use vars qw ($q $sbeams $sbeamsPROT
             $t0 $t1 $t2 $t3 $t4 $t5 $t6 $t7 $t8 $t9
             $current_contact_id $current_username );
use CGI;
use CGI::Carp qw(fatalsToBrowser croak);
use Time::HiRes qw( usleep ualarm gettimeofday tv_interval );
$t0 = [gettimeofday()];

use SBEAMS::Connection;
use SBEAMS::Connection::Settings;
use SBEAMS::Connection::Tables;

use SBEAMS::Proteomics;
use SBEAMS::Proteomics::Settings;
use SBEAMS::Proteomics::Tables;

use PGPLOT;
use PDL;
use PDL::Graphics::PGPLOT;

use File::Basename;

$q = new CGI;
$sbeams = new SBEAMS::Connection;
$sbeamsPROT = new SBEAMS::Proteomics;
$sbeamsPROT->setSBEAMS($sbeams);


###############################################################################
# Define global variables if any and execute main()
###############################################################################
main();


###############################################################################
# Main Program:
#
# If $sbeams->Authenticate() succeeds, print header, process the CGI request,
# print the footer, and end.
###############################################################################
sub main {

    #### Do the SBEAMS authentication and exit if a username is not returned
    exit unless ($current_username = $sbeams->Authenticate());

    #### Print the header, figure and do what the user want, and print footer
    processRequests();
    $sbeamsPROT->printPageFooter();

} # end main


###############################################################################
# Process Requests
#
# Test for specific form variables and process the request
# based on what the user wants to do.
###############################################################################
sub processRequests {
    $current_username = $sbeams->getCurrent_username;
    $current_contact_id = $sbeams->getCurrent_contact_id;


    # Enable for debugging
    if (0==1) {
      print "Content-type: text/html\n\n";
      my ($ee,$ff);
      foreach $ee (keys %ENV) {
        print "$ee =$ENV{$ee}=<BR>\n";
      }
      foreach $ee ( $q->param ) {
        $ff = $q->param($ee);
        print "$ee =$ff=<BR>\n";
      }
    }


    #### Only one view available for this program
    printEntryForm();


} # end processRequests



###############################################################################
# Print Entry Form
###############################################################################
sub printEntryForm {

    #### Define some general variables
    my ($i,$element,$key,$value,$sql);
    $t1 = [gettimeofday()];


    #### Define the parameters that can be passed by CGI
    my @possible_parameters = qw ( msms_scan_id search_batch_id peptide
                                   masstype charge zoom xmin xmax masstol ionlab);
    my %parameters;


    #### Read in all the passed parameters into %parameters hash
    foreach $element (@possible_parameters) {
      $parameters{$element}=$q->param($element);
    }
    my $apply_action  = $q->param('apply_action');


    if ($apply_action eq "PRINTABLE FORMAT") {
      $sbeamsPROT->printPageHeader(navigation_bar=>"NO");
    } else {
      $sbeamsPROT->printPageHeader();
    }

    #### Resolve the keys from the command line if any
    my ($key,$value);
    foreach $element (@ARGV) {
      if ( ($key,$value) = split("=",$element) ) {
        $parameters{$key} = $value;
      } else {
        print "ERROR: Unable to parse '$element'\n";
        return;
      }
    }


    $parameters{'charge'} = "1,2" unless $parameters{'charge'};
    my @charge = split(',',$parameters{'charge'});
    $parameters{'masstol'} = 2 unless $parameters{'masstol'};

    $parameters{'ionlab'} = "Horizontal" unless $parameters{'ionlab'};
    my ($labangle,$fjust);
    if ($parameters{'ionlab'} eq "Vertical") {
      $labangle = 90;
      $fjust = 0;
    } else {
      $labangle = 0;
      $fjust = 0.5;
    }



    #### Begin the page and form
    print "<TABLE><TD>\n";
    $sbeams->printUserContext();
    print "</TD></TABLE>\n";
    print qq!
	<P>
	<FORM METHOD="post">
    !;


    #### Set up the table and data column
    print qq!
	<TABLE BORDER=1 WIDTH="675">
	<TR VALIGN=top>
	<TD VALIGN=top BGCOLOR="#FFFFDD">
	<PRE>\n!;


    #### Display the ions table here

    #### If we have a search_batch_id, find the mass modifications
    my %mass_modifications;
    if ($parameters{search_batch_id}) {
      %mass_modifications =
        get_mass_modifications(search_batch_id=>$parameters{search_batch_id});
    }
    $t2 = [gettimeofday()];


    #### Calculate peptide mass information
    my $masstype = $parameters{masstype} || 0;
    my ($AAmasses_ref) = InitializeMass($masstype);


    #### Update peptide mass information
    #### First loop through static modifications
    foreach (keys %mass_modifications) {
      $AAmasses_ref->{$_} = $mass_modifications{$_} if /^\w$/;
    }
    #### Now loop through to get dynamic modifications
    foreach (keys %mass_modifications) {
      $AAmasses_ref->{$_} = $AAmasses_ref->{$1} + $mass_modifications{$_} if /^(\w)\W$/;
    }

    my %spectrum = get_msms_spectrum(msms_scan_id=>$parameters{msms_scan_id});
    unless (%spectrum) {
      print "ERROR: Unable to load spectrum\n";
      return;
    }
    $t3 = [gettimeofday()];

    my ($i,$mass,$intensity,$massmin,$xticks,$xmin,$xmax);
    my ($massmax,$intenmax)=(0,0);
    $parameters{zoom} = 1 unless $parameters{zoom};

    my $peptide = $parameters{peptide};
    $peptide =~ s/^.\.//;
    $peptide =~ s/\..$//;


    for ($i=0; $i<$spectrum{n_peaks}; $i++) {
      $mass = $spectrum{masses}->[$i];
      $intensity = $spectrum{intensities}->[$i];
      $massmin = $mass if ($i == 0);
      $massmax = $mass if ($mass > $massmax);
      $intenmax = $intensity if ($intensity > $intenmax);
    }

    #### Compute data and plot bounds
    $parameters{xmin} = int($massmin/100)*100 unless $parameters{xmin};
    $parameters{xmax} = int($massmax/100)*100+100 unless $parameters{xmax};

    my $maxval = $intenmax;
    $intenmax *= 1.1 / $parameters{zoom};
    my $interval = $intenmax / 20;
    my $interval_power = int( log($interval) / log(10) );
    my $roundval = 10**$interval_power;
    $intenmax = int($intenmax/$roundval)*$roundval;
    my $ydiv = $intenmax / 2;

    #### Calculate fragment ions for the given peptide
    my @residues = Fragment($peptide);
    my $length = scalar(@residues);


    #### Initialize the plot environment
    my($progname)= basename $0;
    my($tmpfile) = "$progname.$$.@{[time]}.gif";

    $parameters{gifwidth} = 640 unless $parameters{gifwidth};
    $parameters{gifheight} = 480 unless $parameters{gifheight};

    if ($apply_action eq "PRINTABLE FORMAT") {
      $parameters{gifwidth} = 480;
      $parameters{gifheight} = 384;
    }

#    print "Writing GIF to: $PHYSICAL_BASE_DIR/images/tmp/$tmpfile\n";
    my $win = pg_setup(Device=>"$PHYSICAL_BASE_DIR/images/tmp/$tmpfile/gif",
                       title=>"$spectrum{msms_scan_file_root}",
                       xmin=>$parameters{xmin}, xmax=>$parameters{xmax},
                       ymax=>$intenmax, ydiv=>$ydiv, nyticks=>1,
                       gifwidth=>$parameters{gifwidth},gifheight=>$parameters{gifheight});
    pgmtext 'T',-2,.01,0,"Peak value = $maxval";
    $t4 = [gettimeofday()];

    my @peakcolors;

    my $charge;
    foreach $charge (@charge) {
      my ($masslist_ref) = CalcIons(Residues=>\@residues, Charge=>$charge,
                                    MassArray=>$AAmasses_ref);
      my ($B_ref,$Y_ref);
      $t5 = [gettimeofday()];

      #### Make the plot
      ($win,$B_ref,$Y_ref) = PlotPeaks(SpecData=>\%spectrum,
                                       Masslist=>$masslist_ref, Charge=>$charge,
                                       Win=>$win, Length=>$length,
                                       Window=>$parameters{masstol},
                                       PeakColors=>\@peakcolors);
      $t6 = [gettimeofday()];
      PrintIons(Masslist=>$masslist_ref,Color=>1,Html=>1,Charge=>$charge,Length=>$length);

      LabelResidues(Ionmasses=>$masslist_ref, Binten=>$B_ref, Yinten=>$Y_ref,
                    Charge=>$charge, Win=>$win, Length=>$length,
                    Xmin=>$parameters{xmin}, Xmax=>$parameters{xmax},
                    Ymax=>$intenmax, Angle=>$labangle, Fjust=>$fjust);
    }
    $t7 = [gettimeofday()];


    #### Finish and close the plot
    $win->close();


    #### Set up the image cell
    print qq~</PRE>
	</TD>
	<TD VALIGN=top>
	<IMG SRC="$HTML_BASE_DIR/images/tmp/$tmpfile"><BR>
    ~;


    #### Print static input paramters as hidden fields
    foreach $element ( qw ( msms_scan_id search_batch_id peptide masstype ) ) {
      if ($parameters{$element}) {
        print qq~<INPUT TYPE="hidden" NAME="$element" VALUE="$parameters{$element}">\n~;
      }
    }

    #### Charge selector
    my $onChange = "";
    $sql = "SELECT option_key,option_value FROM $TBPR_QUERY_OPTION " .
           " WHERE option_type = 'BSH_charge_constraint' " .
           " ORDER BY sort_order,option_value";
    my $optionlist = $sbeams->buildOptionList($sql,$parameters{'charge'});
    print qq~
	Charge: <SELECT NAME="charge" $onChange>
	$optionlist</SELECT>
    ~;

    #### Zoom selector
    print qq~
	Zoom: <INPUT NAME="zoom" VALUE="$parameters{zoom}" SIZE="2" $onChange>
    ~;

    #### Xmin selector
    print qq~
	Xmin: <INPUT NAME="xmin" VALUE="$parameters{xmin}" SIZE="5" $onChange>
    ~;

    #### Xmax selector
    print qq~
	Xmax: <INPUT NAME="xmax" VALUE="$parameters{xmax}" SIZE="5" $onChange><BR>
    ~;

    #### Window selector
    print qq~
	Mass Tolerance: <INPUT NAME="masstol" VALUE="$parameters{masstol}" SIZE="2" $onChange>
    ~;

    #### Label orientation
    my @labellist = (qw (Vertical Horizontal));
    my ($ll, $selflag);
    print qq~
        Label orientation: <SELECT NAME="ionlab">
    ~;
    foreach $ll (@labellist) {
      if ($parameters{ionlab} eq $ll) {
        $selflag = "SELECTED";
      } else {
        $selflag = "";
      }
      print qq~
          <OPTION $selflag VALUE="$ll">$ll</OPTION>
      ~;
    }
    print qq~
        </SELECT>
    ~;

    #### Finish up the table and form
    $t8 = [gettimeofday()];
    print qq~<BR>
	&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;
	<INPUT TYPE="submit" NAME="apply_action" VALUE="REFRESH">
        <INPUT TYPE="submit" NAME="apply_action" VALUE="PRINTABLE FORMAT">
	</TD>
	</TR>
	</TABLE>
         </FORM>
    ~;

#    printf("\nt0 - t1: %4f<BR>\n",tv_interval($t0,$t1));
#    printf("t1 - t2: %4f<BR>\n",tv_interval($t1,$t2));
#    printf("t2 - t3: %4f<BR>\n",tv_interval($t2,$t3));
#    printf("t3 - t4: %4f<BR>\n",tv_interval($t3,$t4));
#    printf("t4 - t5: %4f<BR>\n",tv_interval($t4,$t5));
#    printf("t5 - t6: %4f<BR>\n",tv_interval($t5,$t6));
#    printf("t6 - t7: %4f<BR>\n",tv_interval($t6,$t7));
#    printf("t7 - t8: %4f<BR>\n",tv_interval($t7,$t8));
#    printf("  Total: %4f<BR>\n",tv_interval($t0,$t8));


} # end printEntryForm


###############################################################################
# get_msms_spectrum
###############################################################################
sub get_msms_spectrum {
  my %args = @_;

  my $inputfile = $args{'inputfile'} || "";
  my $verbose = $args{'verbose'} || "";
  my $msms_scan_id = $args{'msms_scan_id'} || "";


  #### Define some general variables
  my ($i,$element,$key,$value,$sql);
  my (@rows,$nrows);


  #### Define the data hash
  my %spectrum;
  my @mass_intensities;


  #### If we have a msms_scan_id, get the data from the database
  if ($msms_scan_id) {

    #### Define the columns for
    my @columns = qw ( msms_scan_id fraction_id msms_scan_file_root
      start_scan end_scan n_peaks );


    #### Extract the information about the spectrum from database
    $sql = "SELECT " . join(",",@columns) .
           "  FROM $TB_MSMS_SCAN ".
           " WHERE msms_scan_id = '$msms_scan_id'";
    @rows = $sbeams->selectSeveralColumns($sql);
    $nrows = scalar(@rows);


    #### If we didn't get exactly one row, complain and return
    if ($nrows != 1) {
      print "\nERROR: Unable to find msms_scan_id '$msms_scan_id'.\n\n"
        unless ($nrows);
      print "\nERROR: Got too may results ($nrows rows) looking for ".
        "msms_scan_id '$msms_scan_id'.\n\n"
        if ($nrows > 1);
      return;
    }


    #### Store result in data hash
    $i = 0;
    foreach $element (@columns) {
      $spectrum{$element} = $rows[0]->[$i];
      $i++;
    }


    #### Extract the actual mass,intensity pairs from database
    $sql = "SELECT mass,intensity ".
           "  FROM $TB_MSMS_SPECTRUM_PEAK ".
           " WHERE msms_scan_id = '$msms_scan_id'";
    my @mass_intensities = $sbeams->selectSeveralColumns($sql);
    unless (@mass_intensities) {
      print "\nERROR: Unable to find msms_scan_id '$msms_scan_id'.\n\n";
      return;
    }


    #### Verify that n_peaks is correct
    unless (scalar(@mass_intensities) == $spectrum{n_peaks}) {
      print "\nWARNING: Number of data points returned does not match n_peaks.\n\n";
      return;
    }


    #### Extract rows into two arrays of masses and intensities
    my (@masses,@intensities);
    for ($i=0; $i<$spectrum{n_peaks}; $i++) {
      push(@masses,$mass_intensities[$i]->[0]);
      push(@intensities,$mass_intensities[$i]->[1]);
    }

    #### Put data into hash and return
    $spectrum{masses} = \@masses;
    $spectrum{intensities} = \@intensities;

    return %spectrum;


  #### Otherwise complain and return
  } else {
    print "\nERROR: Unable to determine which msms_scan_id to load.\n\n";
    return;
  }

}


###############################################################################
# get_mass_modifications
###############################################################################
sub get_mass_modifications {
    my %args = @_;

    my $verbose = $args{'verbose'} || "";
    my $search_batch_id = $args{'search_batch_id'} || "";

    unless ($search_batch_id >= 1) {
      print "ERROR: search_batch_id must be a number >= 1\n";
      return;
    }

    #### Define some general variables
    my ($i,$element,$key,$value,$sql_query);
    my %mass_modifications;

    #### Query to find all the static mass modifications for this
    #### search_batch_id
    $sql_query = qq~
	  SELECT parameter_key,parameter_value
	    FROM $TB_SEARCH_BATCH_PARAMETER
	   WHERE search_batch_id = '$search_batch_id'
	     AND parameter_key LIKE 'add%'
	     AND CONVERT(real,parameter_value) != 0
    ~;

    #### Execute the query and store any returned modifications
    my %mods = $sbeams->selectTwoColumnHash($sql_query);
    while ( ($key,$value) = each %mods ) {
      $key =~ /.+\_(\w)\_.+/;
      $mass_modifications{$1} = $value if ($1);
    }

    #### Query to extract the variable mass modifications for this
    ####  search_batch_id
    $sql_query = qq~
	  SELECT parameter_value
	    FROM $TB_SEARCH_BATCH_PARAMETER
           WHERE search_batch_id = '$search_batch_id'
	     AND parameter_key = 'diff_search_options'
    ~;

    #### Execute the query and store any returned modifications
    my ($diff_options) = $sbeams->selectOneColumn($sql_query);
    my @mod_symbols = ( '*', '#', '@' );
    $i = 0;
    while ($diff_options =~ s/\s*([\d\.]+)\s+(\w)//) {
      if ($2){
        $key = uc($2) . $mod_symbols[$i];
        $mass_modifications{$key} = $1;
        $i++;
      }
    }

    return %mass_modifications;
}

###############################################################################
# InitializeMass
###############################################################################
sub InitializeMass {
    my $masstype = shift;
    my %AAmasses = ();
    my ($code, $avg, $mono);

    #### AminoAcidMasses contains the mass info
    open (MASSFILE,'AminoAcidMasses.dat') ||
      carp "unable to open AminoAcidMasses.dat file!\n";
    while (<MASSFILE>) {
      #### Ignore header line
      next if /^CODE/;
      ($code,$avg,$mono) = split;
      if ($masstype) {
        $AAmasses{$code} = $mono;
      } else {
        $AAmasses{$code} = $avg;
      }
    }

    close MASSFILE;
    #### Return references to AAmasses
    return (\%AAmasses);
}

###############################################################################
# pg_setup
###############################################################################
sub pg_setup {
    my %args = @_;

    #### Default device is to screen (xserver)
    my $device = $args{'Device'} || "\/xs";
    #$device = "/xs";

    #### Plot title
    my $title = $args{'title'} || "";

    #### Default x limits are (0,2000)
    my $xmin = $args{'xmin'} || 0;
    my $xmax = $args{'xmax'} || 2000;

    #### Default y limits are (0,500000)
    my $ymin = $args{'ymin'} || 0;
    my $ymax = $args{'ymax'} || 500000;

    #### Default separation between ticks is 100000
    my $ytickdiv = $args{'ydiv'} || 100000;

    #### Default number of y ticks
    my $nyticks = $args{'nyticks'}+1 || 4;

    #### Default image size is 640x480
    my $gifwidth = $args{'gifwidth'} || 640;
    my $gifheight = $args{'gifheight'} || 480;

    #### Set needed PGPLOT environment variables
    $ENV{"PGPLOT_GIF_WIDTH"} = $gifwidth;
    $ENV{"PGPLOT_GIF_HEIGHT"} = $gifheight;
    $ENV{"PGPLOT_BACKGROUND"} = "lightyellow";

    #### Create a new graphics device
    my $win = PDL::Graphics::PGPLOT::Window -> new({Device => "$device"});

    #### Set window limits
    pgswin $xmin, $xmax, 0, $ymax;

    #### Set viewport limits
    pgsvp .095,.9775,.065,.95;

    #### Set axis color to black (stealing lt. gray color)
    pgscr 15, 0,0,0;

    #### Set color index
    pgsci 15;

    #### Set character height
    pgsch .8;

    #### Set line width
    pgslw 1;

    #### Set character font (Normal)
    pgscf 1;

    #### Draw labeled frame around viewport: full frame (BC), labels on
    #### bottom and left of frame (N), major tick marks (T), y labels
    #### normal to y-axis (V), decimal labels instead of scientific
    #### notation (1), automatic x major ticks, $ytickdiv between y ticks,
    #### with $nyticks major divisions.
    pgbox 'BCNT',0,0,'BCNTV1',$ytickdiv,$nyticks;

    #### Reset character height (make labels larger)
    pgsch 1;

    #### Y label on left, centered vertically along axis
    pgmtxt 'L',3.8,.5,.5,'Intensity';

    #### X label on bottom, centered vertically along axis
    pgmtxt 'B',2.25,.5,.5,'m/z';

    #### Main title above, centered vertically along top
    pgmtxt 'T',1,.5,.5,"$title";

    #### Reset character height (want in-plot labels small)
    pgsch .8;

    #### Allow overplotting of this frame
    $win -> hold;

    return $win;
}

###############################################################################
# PlotPeaks
###############################################################################
sub PlotPeaks {
    my %args = @_;

    #### Spectrum data to be plotted
    my $specdata = $args{'SpecData'};

    #### Ions to be plotted
    my $masslist_ref = $args{'Masslist'};

    #### Charge
    my $charge = $args{'Charge'};

    #### Plot frame
    my $win = $args{'Win'};

    #### Peak Colors
    my $peakcolors_ref = $args{'PeakColors'};

    #### Peak finding window
    my $window = $args{'Window'} || 2;

    my $length = $args{'Length'};
    my @Binten = (0) x $length;
    my @Yinten = (0) x $length;
    my @BYinten = (0) x $length;
    my @Rinten = (0) x $specdata->{n_peaks};
    my @Bmass = (0) x $length;
    my @Ymass = (0) x $length;
    my @BYmass = (0) x $length;

    my ($redcol,$bluecol,$grcol);

    #### Define pink color to be lightcoral
    pgscr 6,0.94,0.5,0.5;

    #### Define lt. blue color to be navy
    pgscr 11,0,0,.5;

    #### Define lt. green color to be DarkSeaGreen
    pgscr 10,0.56,0.74,0.56;

    #### Define red color to be red
    pgscr 2,1,0,0;

    #### Define blue color to be blue
    pgscr 4,0,0,1;

    #### Define green color to be ForestGreen
    pgscr 3,0.13,0.55,0.13;

    if ($charge == 1) {
      $redcol = 6;
      $bluecol = 11;
      $grcol = 10;
    }
    elsif ($charge == 2) {
      $redcol = 2;
      $bluecol = 4;
      $grcol = 3;
    }


    #### Convert to piddle for easy sub-selecting
    my $bdata = pdl $masslist_ref->{Bions};
    my $ydata = pdl $masslist_ref->{Yions};

    #### Draw peaks
    my $i;
    my $lineclr;
    my ($mass, $intensity);

    for ($i=0; $i<$specdata->{n_peaks}; $i++) {
      $mass = $specdata->{masses}->[$i];
      $intensity = $specdata->{intensities}->[$i];

      #### Set default line color to Black
      $lineclr = $peakcolors_ref->[$i] || 14;

      my $mainx = pdl [$mass, $mass];
      my $mainy = pdl [0, $intensity];


      #### This kludge lets me not colorize the last B and/or
      #### first Y peaks found
      set $bdata, ($length-1),-9999;
      set $ydata, 0, -9999;

      my $Bind = which($bdata >= ($mass-$window) & $bdata <= ($mass+$window));
      my $Yind = which($ydata >= ($mass-$window) & $ydata <= ($mass+$window));

      if (($Bind !~ 'Empty') && ($Yind =~ 'Empty')) {
        if ($Binten[$Bind->at(0)] < $intensity) {
          $Binten[$Bind->at(0)] = $intensity;
          $Bmass[$Bind->at(0)] = $mass;
          $lineclr = $redcol;
          $masslist_ref->{Bcolor}->[$Bind->at(0)] = $lineclr;
        }
      } elsif (($Yind !~ 'Empty') && ($Bind =~ 'Empty')) {
        if ($Yinten[$Yind->at(0)] < $intensity) {
          $Yinten[$Yind->at(0)] = $intensity;
          $Ymass[$Yind->at(0)] = $mass;
          $lineclr = $bluecol;
          $masslist_ref->{Ycolor}->[$Yind->at(0)] = $lineclr;
        }
      } elsif (($Bind !~ 'Empty') && ($Yind !~ 'Empty')) {
        if ($Yinten[$Yind->at(0)] < $intensity) {
          $BYinten[$Yind->at(0)] = $intensity;
          $BYmass[$Yind->at(0)] = $mass;
          $lineclr = $grcol;
          $masslist_ref->{Bcolor}->[$Yind->at(0)] = $lineclr;
          $masslist_ref->{Ycolor}->[$Yind->at(0)] = $lineclr;
        }
      } else {
        if (($peakcolors_ref->[$i] != 2) & ($peakcolors_ref->[$i] != 3) &
            ($peakcolors_ref->[$i] != 4) & ($peakcolors_ref->[$i] != 6) &
            ($peakcolors_ref->[$i] != 10) & ($peakcolors_ref->[$i] != 11)) {
          $Rinten[$i] = $intensity
        }
        $lineclr = 14;
      }

      $peakcolors_ref->[$i] = $lineclr;
    }

    my ($mass2, $intensity2);
    $mass2 = $specdata->{masses};
    $intensity2 = $specdata->{intensities};

    #### Now we resort to plotting all peaks by "never lifting the pen"
    #### and drawing it all in a continuous line with line() because this
    #### is much faster
    my $rx = pdl ($mass2,$mass2,$mass2)->xchg(0,1)->clump(2);
    my $ra = [(0) x scalar(@Rinten)];
    my $ry = pdl ($ra,\@Rinten,$ra)->xchg(0,1)->clump(2);
    my $rh = {Color => 14};
    $win -> line ($rx,$ry,$rh);

    my $bx = pdl (\@Bmass,\@Bmass,\@Bmass)->xchg(0,1)->clump(2);
    my $ba = [(0) x scalar(@Binten)];
    my $by = pdl ($ba,\@Binten,$ba)->xchg(0,1)->clump(2);
    my $bh = {Color => $redcol};
    $win -> line ($bx,$by,$bh);

    my $yx = pdl (\@Ymass,\@Ymass,\@Ymass)->xchg(0,1)->clump(2);
    my $ya = [(0) x scalar(@Yinten)];
    my $yy = pdl ($ya,\@Yinten,$ya)->xchg(0,1)->clump(2);
    my $yh = {Color => $bluecol};
    $win -> line ($yx,$yy,$yh);

    my $byx = pdl (\@BYmass,\@BYmass,\@BYmass)->xchg(0,1)->clump(2);
    my $bya = [(0) x scalar(@BYinten)];
    my $byy = pdl ($bya,\@BYinten,$ba)->xchg(0,1)->clump(2);
    my $byh = {Color => $grcol};
    $win -> line ($byx,$byy,$byh);

    return ($win,\@Binten,\@Yinten);
}


###############################################################################
# LabelResidues
###############################################################################
sub LabelResidues {
    my %args = @_;

    my $Ionmasses_ref = $args{'Ionmasses'};
    my $Bdata = pdl $Ionmasses_ref->{Bions};
    my $Ydata = pdl $Ionmasses_ref->{Yions};
    my $charge = $args{'Charge'};
    my $win = $args{'Win'};
    my $Binten_ref = $args{'Binten'};
    my @Binten = @$Binten_ref;
    my $Yinten_ref = $args{'Yinten'};
    my @Yinten = @$Yinten_ref;
    my $length = $args{'Length'};
    my $labht;
    my $angle = $args{'Angle'} || 0;
    my $fjust = $args{'Fjust'};
    my ($Bcol,$Ycol,$bothcol);
    my $i;
    my ($lineclr,$redcol,$bluecol,$grcol);
    my $Ymax = $args{'Ymax'};
    my $Xmin = $args{'Xmin'};
    my $Xmax = $args{'Xmax'};
    my $interval;

    #### Define pink color to be lightcoral
    pgscr 6,0.94,0.5,0.5;

    #### Define lt. blue color to be navy
    pgscr 11,0,0,.5;

    #### Define lt. green color to be DarkSeaGreen
    pgscr 10,0.56,0.74,0.56;

    #### Define red color to be lightcoral
    pgscr 2,1,0,0;

    #### Define blue color to be navy
    pgscr 4,0,0,1;

    #### Define green color to be DarkSeaGreen
    pgscr 3,0.13,0.55,0.13;

    if ($charge == 1) {
      $redcol = 6;
      $bluecol = 11;
      $grcol = 10;
    }
    elsif ($charge == 2) {
      $redcol = 2;
      $bluecol = 4;
      $grcol = 3;
    }

    for ($i=0; $i < $length; $i++) {
      if (($Binten[$i] != 0) && ($i != ($length-1))) {
        my $val = $Ionmasses_ref->{indices}->[$i];
        ++$val;
        my $index = "B$charge\-$val";
        my $mass = $Bdata->at($i);
        my $matchx = pdl [$mass, $mass];
        my $y = $Binten[$i];
        my $matchy = pdl [$y+($interval/3.), $y+4*($interval/3.)];
        my $Yind = which($Ydata >= ($mass-2) & $Ydata <= ($mass+2));
        if ($Yind !~ 'Empty') {
          #### Green text and line for both ion match
          pgsci $grcol;
          $lineclr = $grcol;

          #### Location of label above tick mark (moved up)
          $labht = $y+6.5*($interval/3.);
        } else {
          #### Red text and line for B ion match
          pgsci $redcol;
          $lineclr = $redcol;

          #### Location of label above tick mark
          $labht = $y+5*($interval/3.);
        }
        #### Plot ion marker line
        $win -> line($matchx, $matchy, {Color=>$lineclr});
        $win -> hold;

        #### Add ion label
        pgptext $mass,$labht,$angle,$fjust,"$index" if (($labht < $Ymax) && ($mass > $Xmin)
                                                  && ($mass < $Xmax));
      }
      if (($Yinten[$i] != 0) && ($i != 0)) {
        my $index = "Y$charge\-$Ionmasses_ref->{rev_indices}->[$i]";
        my $mass = $Ydata->at($i);
        my $matchx = pdl [$mass, $mass];
        my $y = $Yinten[$i];
        my $matchy = pdl [$y+($interval/3.), $y+4*($interval/3.)];
        my $Bind = which($Bdata >= ($mass-2) & $Bdata <= ($mass+2));
        if ($Bind !~ 'Empty') {
          #### Green text and line for both ion match
          pgsci $grcol;
          $lineclr = $grcol;

          #### Location of label above tick mark
          $labht = $y+5*($interval/3.);
        } else {
          #### Blue text and line for Y ion match
          pgsci $bluecol;
          $lineclr = $bluecol;

          #### Location of label above tick mark
          $labht = $y+5*($interval/3.);
        }
        #### Plot ion marker line
        $win -> line($matchx, $matchy, {Color=>$lineclr});
        $win -> hold;

        #### Add ion label
        pgptext $mass,$labht,$angle,$fjust,"$index" if (($labht < $Ymax) && ($mass > $Xmin)
                                                  && ($mass < $Xmax));
      }
    }
    return $win;
}

###############################################################################
# Fragment
###############################################################################
sub Fragment {
    my $peptide = shift;
    my $length = length($peptide);
    my @residues = ();
    my $i;

    for ($i=0; $i<$length; $i++) {
      if (substr($peptide,$i+1,1) =~ /\W/) {
        push (@residues, substr($peptide,$i,2));
        $i = $i + 1;
      } else {
        push (@residues, substr($peptide,$i,1));
      }
    }

    #### Return residue array
    return @residues;
}

###############################################################################
# CalcIons
###############################################################################
sub CalcIons {
    my %args = @_;
    my $i;

    my $residues_ref = $args{'Residues'};
    my @residues = @$residues_ref;
    my $charge = $args{'Charge'} || 1;
    my $massarray_ref = $args{'MassArray'};
    my %massarray = %$massarray_ref;
    my $length = scalar(@residues);

    my $Nterm = $massarray{"h"};
    my $Bion = 0;
    my $Yion  = 2 * $Nterm + $massarray{"o"};

    my @Bcolor = (14) x $length;
    my @Ycolor = (14) x $length;

    for ($i=0; $i<$length; $i++) {
      $Yion += $massarray{$residues[$i]};
    }

    my %masslist;
    my (@aminoacids, @indices, @rev_indices, @Bions, @Yions);

    #### Compute the ion masses
    for ($i = 0; $i<$length; $i++) {
      $Bion += $massarray{$residues[$i]};
      $Yion -= $massarray{$residues[$i-1]} if ($i > 0);

      #### B index & Y index
      $indices[$i] = $i;
      $rev_indices[$i] = $length-$i;

      #### B ion mass & Y ion mass
      $Bions[$i] = ($Bion + $charge*$Nterm)/$charge;
      $Yions[$i] = ($Yion + $charge*$Nterm)/$charge;
    }

    $masslist{residues} = \@residues;
    $masslist{indices} = \@indices;
    $masslist{Bions} = \@Bions;
    $masslist{Yions} = \@Yions;
    $masslist{rev_indices} = \@rev_indices;

    #### Return reference to a hash of array references
    return (\%masslist);
}

###############################################################################
# PrintIons
###############################################################################
sub PrintIons {
    my %args = @_;

    my $masslist_ref = $args{'Masslist'};
    my $color = $args{'Color'} || 0;
    my $html = $args{'Html'} || 0;
    my $charge = $args{'Charge'};
    my $length = $args{'Length'};

    print "\n";
    print " SEQ  #       B         Y    +$charge\n";
    print " --- --  --------- --------- --\n";

    my ($bcolbegin, $bcolend, $ycolbegin, $ycolend);

    my (%colors);
    $colors{2} = "FF0000";
    $colors{4} = "0000FF";
    $colors{3} = "218D21";
    $colors{6} = "F18080";
    $colors{11} = "00080";
    $colors{10} = "8FBE8F";


    #### Printing stuff
    for (my $i=0; $i < $length; $i++) {
      if ($html != 0) {
        if ($masslist_ref->{Bcolor}->[$i] >= 2) {
          $bcolbegin = "<FONT COLOR = $colors{$masslist_ref->{Bcolor}->[$i]}>";
          $bcolend = "</FONT>";
        } else {
          $bcolbegin = "<FONT COLOR = black>";
          $bcolend = "</FONT>";
        }
        if ($masslist_ref->{Ycolor}->[$i] >= 2) {
          $ycolbegin = "<FONT COLOR = $colors{$masslist_ref->{Ycolor}->[$i]}>";
          $ycolend = "</FONT>";
        } else {
          $ycolbegin = "<FONT COLOR = black>";
          $ycolend = "</FONT>";
        }
      }
      if ($i == 0) {
        printf " %3s %2d $bcolbegin%9.1f$bcolend %9s %3d\n",$masslist_ref->{residues}->[$i],
                 $i+1, $masslist_ref->{Bions}->[$i], '--  ', $length-$i
      }
      elsif ($i == ($length-1)) {
        printf " %3s %2d %9s $ycolbegin%9.1f$ycolend %3d\n",$masslist_ref->{residues}->[$i], $i+1,
                 '--  ', $masslist_ref->{Yions}->[$i], $length-$i
      }
      else {
        printf " %3s %2d $bcolbegin%9.1f$bcolend $ycolbegin%9.1f$ycolend %3d\n",
                 $masslist_ref->{residues}->[$i], $i+1,
                 $masslist_ref->{Bions}->[$i], $masslist_ref->{Yions}->[$i], $length-$i;
      }
    }
}
