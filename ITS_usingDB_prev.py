from ObjectJSONEncoder import ObjectJSONEncoder
from PloiDbContext import PloiDbContext
from ploidbCommon import *
import time
import pandas as pd
import os
import re
import glob
from Bio.Seq import Seq
from Bio.SeqRecord import SeqRecord
from Bio.Alphabet import IUPAC
from handleMultAccessions import get_taxon_gis_key
from buildTaxaTree import perform_filter_msa

__author__ = 'ItayM3'

#This function will calc the longest seq for each type: its1/its2/combined:
def calc_longest_accordingToType(context):
	# calc avg length of each type:
	com_avg_length = 0;	comb_total = 0;	comb_count = 0
	its1_avg_len = 0; its1_total = 0; its1_count = 0
	its2_avg_len = 0; its2_total = 0; its2_count = 0
	for id in context.its_accession_ids:
		if id in context.its_accession_vs_type:
			if context.its_accession_vs_type[id] == 'combined':
				comb_total += context.its_accession_vs_length[id]
				comb_count += 1
			if context.its_accession_vs_type[id] == 'its1':
				its1_total += context.its_accession_vs_length[id]
				its1_count += 1
			if context.its_accession_vs_type[id] == 'its2':
				its2_total += context.its_accession_vs_length[id]
				its2_count += 1
	if comb_count != 0:
		context.its_type_avg_len['combined'] = comb_total / comb_count
	else:
		context.its_type_avg_len['combined'] = 0
	if its1_count != 0:
		context.its_type_avg_len['its1'] = its1_total / its1_count
	else:
		context.its_type_avg_len['its1'] = 0
	if its2_count != 0:
		context.its_type_avg_len['its2'] = its2_total / its2_count
	else:
		context.its_type_avg_len['its2'] = 0
	logger.debug("Summary of ITS type:\n")
	logger.debug("Combined count: %d, avg length: %f\n" % (comb_count, context.its_type_avg_len['combined']))
	logger.debug("ITS1 count: %d, avg length: %f\n" % (its1_count, context.its_type_avg_len['its1']))
	logger.debug("ITS2 count: %d, avg length: %f\n" % (its2_count, context.its_type_avg_len['its2']))

	return

def get_acc_from_id(acccession_id_line):

	#get accesion id from line like: gi|AF318735.1|taxonid|151425|organism|Prunus
	r = re.compile('gi\|(.*?)\|taxonid')
	m = r.search(acccession_id_line)
	if m:
		return m.group(1)
	else:
		logger.debug("FAILED to find accesion id in line (get_acc_from_id)")


#this function will return the id from accession_id_list of the seq with the most similar length of it's type:
def return_longest_seq(context,accession_id_list):

	min_distance = 999999
	selected_id = accession_id_list[0]
	for id in accession_id_list:
		id_type = context.its_accession_vs_type[id]
		id_length = context.its_accession_vs_length[id]
		if abs(float(id_length - context.its_type_avg_len[id_type])) < min_distance:
			logger.debug('return_longest_seq: selected length %d, Avg length %f' %(id_length,context.its_type_avg_len[id_type]))
			selected_id = id

	return selected_id



#create sequence object for the merged sequence created from seq1Obj and seq2Obj
def createMergedSeqObj_py(seq1Obj, seq2Obj, mergedSeq):

	gi1_header=''
	gi2_header=''
	logger.debug("Inside the create merge Seq Obj function: \n\n")
	header1 = seq1Obj.description
	header2 = seq2Obj.description
	logger.debug(header1)
	logger.debug(header2)
	m1 = re.search('gi\|([^\|]+)\|', header1)
	if m1:
		gi1_header = m1.group(1)
	m2 = re.search('gi\|([^\|]+)\|', header2)
	if m2:
		gi2_header = m2.group(1)

	newHeader = header1 + "|ITS-merge|ITS1:" + gi1_header + " ITS2:" + gi2_header
	logger.debug(newHeader)
	mergedSeqObj = SeqRecord(Seq(mergedSeq),id = gi1_header, description = newHeader)

	logger.debug(newHeader)
	#logger.debug(mergedSeqObj)

	return mergedSeqObj




# append two given sequences (not aligned to each other)
def appendSequences(seq1Obj, seq2Obj):

	appendedSeq = seq1Obj.seq + seq2Obj.seq
	appendedSeqObj = createMergedSeqObj_py(seq1Obj, seq2Obj, appendedSeq)

	return appendedSeqObj


# merge two given aligned sequences (aligned to each other)
def mergeSequences(seq1Obj, seq2Obj):

	indx=0
	mergedSeq_list=[]
	len_seq = len(seq1Obj.seq)
	while indx < len_seq:
		if (seq1Obj.seq[indx] is "-" and seq2Obj.seq[indx] is not "-"):
			mergedSeq_list.append(seq2Obj.seq[indx])
		else:
			mergedSeq_list.append(seq1Obj.seq[indx])
		indx+=1

	merged_seq = ''.join(mergedSeq_list)
	mergedSeqObj = createMergedSeqObj_py(seq1Obj, seq2Obj, merged_seq)

	return mergedSeqObj

def getChosenSequence(ITS1count, ITS2count, seq1Obj, seq2Obj, append):

	chosenSeq = 'None'

	if (ITS1count > 0 and ITS2count > 0):
		if append:
			chosenSeq = appendSequences(seq1Obj, seq2Obj)
		else:
			chosenSeq = mergeSequences(seq1Obj, seq2Obj)
	elif ITS1count > 0 :
		chosenSeq = seq1Obj
	elif ITS2count > 0 :
		chosenSeq = seq2Obj

	return chosenSeq

def ITS_MSA_py(OutDir, ITS1count, ITS2count, combinedCount,ITS1Fasta, ITS2Fasta, combinedFasta,scriptsDir):

	outputFileName = 'None'
	f_msa_its = open(OutDir+'/ITS_msa.log','w')
	f_msa_its.write("About to adjust direction for its sequences\n")

	# combined sequences exist
	if (combinedCount > 0):
		# Adjusting the direction of the relevant fasta files
		if (ITS1count > 0 or ITS2count > 0):
			os.system("cat %s %s > %s/SEP_ITS1+ITS2.fasta" % (ITS1Fasta,ITS2Fasta,OutDir))
			#os.system("cat %s > %s/SEP_ITS1+ITS2.fasta" %(ITS1Fasta,OutDir))
			#os.system("%s >> %s/SEP_ITS1+ITS2.fasta" %(ITS2Fasta,OutDir))

			adjustDirScript = ploidb_config['general']['OTT_MAIN']+'/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s,%s/SEP_ITS1+ITS2.fasta\n" %(adjustDirScript,combinedFasta,OutDir))
			os.system("python %s %s,%s/SEP_ITS1+ITS2.fasta" %(adjustDirScript,combinedFasta,OutDir))
		else:
			adjustDirScript = ploidb_config['general']['OTT_MAIN']+'/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s\n" %(adjustDirScript,combinedFasta))
			os.system("python %s %s" %(adjustDirScript,combinedFasta))


		# create MSA of the combined sequences (contain both ITS1 and ITS2)
		if (combinedCount > 1):
			combined = OutDir + "/combined.msa"
			#os.system("mafft --auto --ep 0.000000 %s > %s" %(combinedFasta,combined))
			exec_external_command_redirect_output("mafft --auto --ep 0.000000 %s > %s" %(combinedFasta,combined))
		elif(combinedCount == 1):
			combined = OutDir + "/combined.msa"
			shutil.copyfile(combinedFasta,combined)
		else:
			combined = "combined.fasta"

		outputFileName = combined
		# if there are separate sequences, add them to the MSA with 'addfragments' option of MAFFT
		if (ITS1count > 0 or ITS2count > 0):
			os.system("mafft --addfragments %s/SEP_ITS1+ITS2.fasta --multipair %s/combined.msa > %s/combined+sep.msa" %(OutDir,OutDir,OutDir))
			outputFileName = OutDir + "/combined+sep.msa"

	# no combined sequences
	else:
		# MSA for ITS1 sequences (if more than one exist)
		if (ITS1count > 1):
			adjustDirScript = ploidb_config['general']['OTT_MAIN']+'/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s\n" %(adjustDirScript,ITS1Fasta))
			os.system("python %s %s" %(adjustDirScript,ITS1Fasta))
			os.system("mafft --auto 0 --ep 0.000000 %s > %s/ITS1_only.msa" %(ITS1Fasta,OutDir))
			# system "mafft --retree 2 --maxiterate 0 --bl 62 --op 1.530000 --ep 0.000000 $ITS1Fasta > OutDir/ITS1_only.msa" ; #-bl 62 , --op 1.530000 -> is default, --ep 0.000000 allows large gaps !!!
			outputFileName = OutDir + "/ITS1_only.msa"
		elif(ITS1count == 1):
			outputFileName = ITS1Fasta

		# MSA for ITS2 sequences (if more than one exist)
		if (ITS2count > 1):
			adjustDirScript = ploidb_config['general']['OTT_MAIN']+'/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s\n" %(adjustDirScript,ITS2Fasta))
			os.system("python %s %s" %(adjustDirScript,ITS2Fasta))
			os.system("mafft --auto 0 --ep 0.000000 %s > %s/ITS2_only.msa" %(ITS2Fasta,OutDir))

			if outputFileName:
				os.system("cat %s > %s/SEP_ITS1+ITS2.msa" %(outputFileName,OutDir))
				os.system("cat %s/ITS2_only.msa >> %s/SEP_ITS1+ITS2.msa" %(OutDir,OutDir))
				outputFileName = OutDir + "/SEP_ITS1+ITS2.msa"
			else:
				outputFileName = OutDir + "/ITS2_only.msa";
		elif(ITS2count == 1):
			if outputFileName:
				os.system("cat %s > %s/SEP_ITS1+ITS2.msa" %(outputFileName,OutDir))
				os.system("cat %s >> %s/SEP_ITS1+ITS2.msa" %(ITS2Fasta,OutDir))
				outputFileName = OutDir + "/SEP_ITS1+ITS2.msa"
			else:
				outputFileName = ITS2Fasta


		# Align SEP_ITS1_ITS2: added bu michal to ensure its aligned file
		os.system("cat %s/SEP_ITS1+ITS2.msa >> %s/SEP_ITS1+ITS2_temp.msa" %(OutDir,OutDir))
		os.system("mafft --auto --quiet %s/SEP_ITS1+ITS2_temp.msa > %s" %(OutDir,outputFileName))

	return outputFileName

def ITS_CLUSTALO_py(OutDir, ITS1count, ITS2count, combinedCount,ITS1Fasta, ITS2Fasta, combinedFasta,scriptsDir):

	outputFileName = 'None'
	f_msa_its = open(OutDir+'/ITS_msa.log','w')
	f_msa_its.write("About to adjust direction for its sequences\n")

	# combined sequences exist
	if (combinedCount > 0):
		# Adjusting the direction of the relevant fasta files
		if (ITS1count > 0 or ITS2count > 0):
			os.system("cat %s %s > %s/SEP_ITS1+ITS2.fasta" % (ITS1Fasta,ITS2Fasta,OutDir))
			#os.system("cat %s > %s/SEP_ITS1+ITS2.fasta" %(ITS1Fasta,OutDir))
			#os.system("%s >> %s/SEP_ITS1+ITS2.fasta" %(ITS2Fasta,OutDir))

			adjustDirScript = ploidb_config['general']['OTT_MAIN'] + '/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s,%s/SEP_ITS1+ITS2.fasta\n" % (adjustDirScript, combinedFasta, OutDir))
			os.system("python %s %s,%s/SEP_ITS1+ITS2.fasta" % (adjustDirScript, combinedFasta, OutDir))
		else:
			adjustDirScript = ploidb_config['general']['OTT_MAIN'] + '/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s\n" % (adjustDirScript, combinedFasta))
			os.system("python %s %s" % (adjustDirScript, combinedFasta))

		# create MSA of the combined sequences (contain both ITS1 and ITS2) - ClastaO
		if (combinedCount > 1):
			combined = OutDir + "/combined.msa"
			MSA_cmd = '%s -i %s -o %s --outfmt=fasta' % (ploidb_config['diff_soft']['ClastaO'], combinedFasta, combined)
			exec_external_command_redirect_output(MSA_cmd)
		elif(combinedCount == 1):
			combined = OutDir + "/combined.msa"
			shutil.copyfile(combinedFasta,combined)
		else:
			combined = "combined.fasta"

		outputFileName = combined
		# if there are separate sequences, add them to the MSA with 'addfragments' option of MAFFT
		if (ITS1count > 0 or ITS2count > 0):
			os.system("mafft --addfragments %s/SEP_ITS1+ITS2.fasta --multipair %s/combined.msa > %s/combined+sep.msa" %(OutDir,OutDir,OutDir))
			outputFileName = OutDir + "/combined+sep.msa"

	# no combined sequences
	else:
		# MSA for ITS1 sequences (if more than one exist)
		if (ITS1count > 1):
			adjustDirScript = ploidb_config['general']['OTT_MAIN']+'/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s\n" %(adjustDirScript,ITS1Fasta))
			os.system("python %s %s" %(adjustDirScript,ITS1Fasta))
			os.system("mafft --auto 0 --ep 0.000000 %s > %s/ITS1_only.msa" %(ITS1Fasta,OutDir))
			# system "mafft --retree 2 --maxiterate 0 --bl 62 --op 1.530000 --ep 0.000000 $ITS1Fasta > OutDir/ITS1_only.msa" ; #-bl 62 , --op 1.530000 -> is default, --ep 0.000000 allows large gaps !!!
			outputFileName = OutDir + "/ITS1_only.msa"
		elif(ITS1count == 1):
			outputFileName = ITS1Fasta

		# MSA for ITS2 sequences (if more than one exist)
		if (ITS2count > 1):
			adjustDirScript = ploidb_config['general']['OTT_MAIN']+'/adjustDirFasta.py'
			f_msa_its.write("Calling: python %s -i %s\n" %(adjustDirScript,ITS2Fasta))
			os.system("python %s %s" %(adjustDirScript,ITS2Fasta))
			os.system("mafft --auto 0 --ep 0.000000 %s > %s/ITS2_only.msa" %(ITS2Fasta,OutDir))

			if outputFileName:
				os.system("cat %s > %s/SEP_ITS1+ITS2.msa" %(outputFileName,OutDir))
				os.system("cat %s/ITS2_only.msa >> %s/SEP_ITS1+ITS2.msa" %(OutDir,OutDir))
				outputFileName = OutDir + "/SEP_ITS1+ITS2.msa"
			else:
				outputFileName = OutDir + "/ITS2_only.msa";
		elif(ITS2count == 1):
			if outputFileName:
				os.system("cat %s > %s/SEP_ITS1+ITS2.msa" %(outputFileName,OutDir))
				os.system("cat %s >> %s/SEP_ITS1+ITS2.msa" %(ITS2Fasta,OutDir))
				outputFileName = OutDir + "/SEP_ITS1+ITS2.msa"
			else:
				outputFileName = ITS2Fasta


		# Align SEP_ITS1_ITS2: added bu michal to ensure its aligned file
		os.system("cat %s/SEP_ITS1+ITS2.msa >> %s/SEP_ITS1+ITS2_temp.msa" %(OutDir,OutDir))
		os.system("mafft --auto --quiet %s/SEP_ITS1+ITS2_temp.msa > %s" %(OutDir,outputFileName))

	return outputFileName



#Perform Blast on fasta (with one ITS type) to choose the representetive seq of this type.
# The other seqs will be removed:
def pickSeqRecord_py(context,fileName,outDir):

	#Need to add the code  so we'll have the length of each type in case the blast results are not definit we
	# can use this criteria to choose the representetiv seq
	accession_id_list=[] # list of accessions to be blasted
	records_list = list(SeqIO.parse(fileName, "fasta"))
	missing_accessions = dict()  # 0 missing, 1 exist
	accession_id_vs_SeqRecord = dict()
	for seq in records_list:
		acc_id = getPropertyFromFastaSeqHeader(seq.description, "gi")
		accession_id_list.append(acc_id)
		accession_id_vs_SeqRecord[acc_id] = seq
	logger.debug("accession_id_list")
	logger.debug(accession_id_list)

	if len(records_list) > 1:
		logger.debug("File name - %s, len(records_list) - %d" %(fileName,len(records_list)))
		type_name = os.path.basename(fileName) # combined/ITS1/ITS2
		blast_file = outDir + '/' + type_name + '_all_v_all.blastn'
		os.system("formatdb -i %s -pF" %fileName)
		os.system("blastall -p blastn -d %s -i %s -v 100000 -b 100000 -e 1e-5 -m 8 > %s" %(fileName,fileName,blast_file))
		f_blastResults = open(blast_file)
		logger.debug("Generating dictionary of bitscores between seqs according to %s" % blast_file)

		dr = csv.DictReader(f_blastResults, delimiter='\t',fieldnames=['query_id','subject_id','pct_identity','align_len','mismatches',
															  'gap_openings','q_start','q_end','s_start','s_end','eval','bitscore'])
		rowslist = list(dr)

		#For each pair save the score in dict: check that all accession are here:
		accession_pair_vs_MaxScore=dict()
		pairs_list=[]
		min_score=999999
		for row in rowslist:
			score_list=[]
			query_id=get_acc_from_id(row['query_id'])
			subj_id = get_acc_from_id(row['subject_id'])
			pair_key = get_taxon_gis_key(query_id,subj_id)
			pairs_list.append(pair_key)
			score = float(row['bitscore'])
			if score < min_score:	#save minimum score:
				min_score = score
			#save all score results of this pair as a list:
			if pair_key not in accession_pair_vs_MaxScore:
				score_list.append(float(score))
				accession_pair_vs_MaxScore[pair_key] = score_list
			else:
				score_list = list(accession_pair_vs_MaxScore[pair_key])
				score_list.append(float(score))
				accession_pair_vs_MaxScore[pair_key] = score_list
			logger.debug(score_list)
		logger.debug("accession_pair_vs_MaxScore:")
		for key in accession_pair_vs_MaxScore:
			logger.debug(key)
			logger.debug(accession_pair_vs_MaxScore[key])
		logger.debug("pairs_list:")
		logger.debug(pairs_list)
		logger.debug("min score:")
		logger.debug(min_score)

		#calculating the max, of all avg values. The value is an avg of all scores of each accession.
		#In case there are no results for some pairs we need to set them as min score
		max_avg_accessionId=0
		max_avg=0
		for accession_id in accession_id_list:
			accession_list_withoutHead = list(accession_id_list)
			accession_list_withoutHead.remove(accession_id)
			sub_id_list=[]
			logger.debug("accession_list_withoutHead:")
			logger.debug(accession_list_withoutHead)
			logger.debug("Calc avg for accession id: %s" %accession_id)
			for pair in pairs_list:
				query_id = pair.split('$')[0]
				sub_id = pair.split('$')[1]
				if accession_id in query_id and accession_id not in sub_id:
					sub_id_list.insert(0,sub_id)
					score_list = list(accession_pair_vs_MaxScore[pair])
					avg_total=0;cnt=0
					for score in score_list:
						avg_total+=score
						cnt+=1
					if avg_total != 0:
						avg=avg_total/cnt
					if avg > max_avg:
						max_avg = avg
						max_avg_accessionId=accession_id
				else: # Only result for the accession vs itself
					score_list = list(accession_pair_vs_MaxScore[pair])
					avg_total=0;cnt=0
					for score in score_list:
						avg_total+=score
						cnt+=1
					if avg_total != 0:
						avg=avg_total/cnt
					if avg > max_avg:
						max_avg = avg#
						max_avg_accessionId=accession_id

			#logger.debug("sub_id_list")
			#logger.debug(sub_id_list)
			#if sub_id_list:	# Check that it is not empty:
			#	for id in accession_list_withoutHead:
			#		logger.debug('id')
			#		logger.debug(id)
			#		if id in sub_id_list:
			#			continue
			#		else:
			#			logger.debug("Missing Accession from Blast Results !!!")
			#			return


		logger.debug("max_avg, accession_id")
		logger.debug("%s,%s" %(max_avg,max_avg_accessionId))

		logger.debug("Selected Accession with highest blast Bitscore is %s" % max_avg_accessionId)
		#check if max_avg_accessionId is 0 -> then we need to select according to length:
		#This case happens when there are no blast results for any of the accessions pairs:
		if max_avg_accessionId == 0:
			accession_id_longest = return_longest_seq(context,accession_id_list)
			logger.debug("(length criteria) Found selected sequence with accession id %s" % accession_id_longest)
			return accession_id_vs_SeqRecord[accession_id_longest]
		else:
			for seq_record in SeqIO.parse(fileName, "fasta"):
				accession_id = getPropertyFromFastaSeqHeader(seq_record.description, "gi")
				logger.debug(accession_id)
				logger.debug(max_avg_accessionId)
				if str(accession_id) == str(max_avg_accessionId):
					selectedSeq = seq_record
					logger.debug("Found selected sequence with accession id %s" % accession_id)
					return selectedSeq
	else:
		return 0

def getTheFirstSequence_py(fileName):

	for seq_record in SeqIO.parse(fileName, "fasta"):
		return seq_record

def pickFromFile_py(context,count,fileName,outDir):

	logger.debug("749875948759847958749857   -> Inside pickFromFile_py\n\n")
	logger.debug(count)
	logger.debug(fileName)
	logger.debug(outDir)

	if (count > 1):
		seq_record = pickSeqRecord_py(context,fileName,outDir)
	elif(count == 1):
		seq_record = getTheFirstSequence_py(fileName)

	logger.debug(seq_record)

	if seq_record is 0:
		logger.debug("pickFromFile_py - 0")
		logger.debug("   0   ")
	else:
		logger.debug("pickFromFile_py - seq id--------------------------------------")
		logger.debug(seq_record.description)
	return seq_record


#MSAfileName, OutDir, OutDir+"/oneSeqPerSpecies.msa", scriptsDir, pickFromMSAlog,append
def pickOneSeqPerSpeciesMSA(context, inputFile, outDir, outputFile, scriptsDir, logFile,append):

	f_log = open(logFile,'a')
	#open(LOG, ">$logFile") or die
	ITS1count=0
	ITS2count=0
	combinedCount=0

	f_log.write ("Calling2 perl %s/SplitFastaSeqsBySpecies.pl %s %s/species\n" %(scriptsDir,inputFile,outDir));
	os.system("perl %s/SplitFastaSeqsBySpecies.pl %s %s/species" %(scriptsDir,inputFile,outDir))

	f_log.write("context.its_accession_vs_type Dictionary:")

	for key in context.its_accession_vs_type.keys():
		f_log.write('%s: %s\n' %(key,context.its_accession_vs_type[key]))

	f_log.write("outputFile:\n")
	f_log.write(outputFile)
	f_log.write('\n')
	Final_records=[]
	for taxon_fasta_file in glob.glob(outDir+"/species/*.fasta"):

		ITS1count = 0
		ITS2count = 0
		combinedCount = 0

		base_file_name = os.path.basename(taxon_fasta_file)
		speciesDirName = base_file_name.replace('.fasta', '')
		speciesDir = outDir+"/species/" +speciesDirName

		seq_records = SeqIO.parse(taxon_fasta_file,'fasta')
		for seq in seq_records:
			f_log.write(seq.id)
			seq_accession = getPropertyFromFastaSeqHeader(seq.description, "gi")
			#seq_accession = str((seq.id).split('|')[1])
			logger.debug("------ Seq Accesion-----> %s\n" %seq_accession)
			logger.debug("taxon file: %s\n" %taxon_fasta_file)
			if seq_accession in context.its_accession_vs_type:
				f_log.write(context.its_accession_vs_type[seq_accession])
				if context.its_accession_vs_type[seq_accession] is 'combined':
					SeqIO.write(seq, speciesDir + "/combined", "fasta")
					combinedCount+=1
				if context.its_accession_vs_type[seq_accession] is 'its1':
					SeqIO.write(seq, speciesDir + "/ITS1_only", "fasta")
					ITS1count+=1
				if context.its_accession_vs_type[seq_accession] is 'its2':
					SeqIO.write(seq, speciesDir + "/ITS2_only", "fasta")
					ITS2count+=1

		if (ITS1count > 1 or ITS2count > 1 or combinedCount > 1):
			f_log.write("More than a single ITS per type was found in %s" %taxon_fasta_file)
			return Fail
		if ((ITS1count > 1 or ITS2count > 1) and (combinedCount > 0)):
			f_log.write("Combined ITS was found as well as ITS1/ITS2 in %s" % taxon_fasta_file)
			return Fail

		f_log.write("taxon_fasta_file = %s)\n" % taxon_fasta_file)
		f_log.write("Counters are: %d,%d,%d\n" %(combinedCount,ITS1count,ITS2count))
		if combinedCount > 0 :
			# pick a combined sequence if available:
			chosenSeq = pickFromFile_py(context,combinedCount, speciesDir +"/combined", speciesDir)
			Final_records.append(chosenSeq)
			#SeqIO.write(chosenSeq, outputFile, "fasta")
		elif (ITS1count > 0 and ITS2count > 0):
			# else, merge two separated sequences - ITS1 + ITS2:
			seqObj1 = getTheFirstSequence_py(speciesDir +"/ITS1_only")
			seqObj2 = getTheFirstSequence_py(speciesDir +"/ITS2_only")
			f_log.write("Merging/appending ITS1 and ITS2\n")
			chosenSeq = getChosenSequence(1, 1, seqObj1, seqObj2, append)
			Final_records.append(chosenSeq)
			f_log.write("species: ITS1 and ITS2 were merged\n")
		elif (ITS1count > 0) :
			chosenSeq = getTheFirstSequence_py(speciesDir + "/ITS1_only")
			Final_records.append(chosenSeq)
			f_log.write("Using ITS1\n")
		elif (ITS2count > 0) :
			chosenSeq = getTheFirstSequence_py(speciesDir + "/ITS2_only")
			Final_records.append(chosenSeq)
			f_log.write("Using ITS2\n")
		else:
			f_log.write("ERROR - species has no ITS sequence\n")

	#Write all chosen sequences to the final msa:
	SeqIO.write(Final_records, outputFile, "fasta")

	return



#This function split ITS sequences per species, per type and choose a representative sequence for each type:
def pickOneITSTypePerSpeciesFasta_py(context,inputFile, outDir, outputFile, scriptsDir, logFile):

	f_log = open (logFile,'w')
	#Also save the seqs to seperate fasta files:
	total_combined_f = open(outDir+'/combined.fasta','w')
	total_ITS1_f = open(outDir+'/ITS1_only.fasta','w')
	total_ITS2_f = open(outDir+'/ITS2_only.fasta','w')
	total_combined_cnt = 0
	total_its1_cnt = 0
	total_its2_cnt = 0

	f_log.write("Calling1 perl %s/SplitFastaSeqsBySpecies.pl %s %s/species_all\n" %(scriptsDir,inputFile,outDir))
	os.system("perl %s/SplitFastaSeqsBySpecies.pl %s %s/species_all" %(scriptsDir,inputFile,outDir))

	chosenSequences = []

	speciesFiles = glob.glob(outDir+"/species_all/*.*")    #   grep { $_ ne '.' && $_ ne '..' } readdir(SP);
	#out_rec = seq_sep_records = SeqIO.parse(outputFile, 'fasta')    #Bio::SeqIO->new("-file" => ">$outputFile", "-format" => "Fasta");

	species_counter = 0
	chosenSequences = []
	f_log.write("Processing $species\n")
	for seq_file in speciesFiles:
		if('.fasta' in seq_file):
			base_file_name = os.path.basename(seq_file)
			speciesDirName = base_file_name.replace('.fasta','')
		#Find Accessions:
		records = SeqIO.parse(seq_file,'fasta')
		for seq in records:
			accession_id = getPropertyFromFastaSeqHeader(seq.description, "gi")
			context.its_accession_ids.append(accession_id)
		logger.debug("context.its_accession_ids")
		logger.debug(context.its_accession_ids)
		speciesDir = "%s/species_all/%s" %(outDir,speciesDirName)
		speciesForMsaDir = "%s/species/%s" %(outDir,speciesDirName) # For later use

		create_dir_if_not_exists(speciesDir)
		create_dir_if_not_exists(speciesForMsaDir)

		(ITS1count, ITS2count, combinedCount) = splitITS_py(context, speciesDir+'.fasta', speciesDir + "/ITS1_only",speciesDir + "/ITS2_only", speciesDir + "/combined")
		f_log.write("Completed 1st splitITS_py: ITS1count=%d, ITS2count=%d, combinedCount =%d)\n" % (ITS1count, ITS2count, combinedCount))
		context.its_taxa_vs_counts[speciesDir] = [ITS1count, ITS2count, combinedCount]

	#calc longest in case of no blast results:
	calc_longest_accordingToType(context)

	#For each species select representative seq:
	for speciesDir in context.its_taxa_vs_counts:
		ITS1count = context.its_taxa_vs_counts[speciesDir][0]
		ITS2count = context.its_taxa_vs_counts[speciesDir][1]
		combinedCount = context.its_taxa_vs_counts[speciesDir][2]
		if (combinedCount > 0):
			chosen_seq = pickFromFile_py(context,combinedCount, speciesDir + "/combined", speciesDir)
			if chosen_seq is not 0:
				species_counter+=1
				chosenSequences.append(chosen_seq)
				SeqIO.write(chosen_seq, total_combined_f, "fasta")
				total_combined_cnt+=1

		# Else,  merge two separated sequences - ITS1 + ITS2:
		elif(ITS1count > 0 or ITS2count > 0):

			if (ITS1count > 0):
				chosen_seq = pickFromFile_py(context,ITS1count, speciesDir + "/ITS1_only", speciesDir)
				if chosen_seq is not 0:
					species_counter += 1
					chosenSequences.append(chosen_seq)
					SeqIO.write(chosen_seq, total_ITS1_f, "fasta")
					total_its1_cnt += 1

			if (ITS2count > 0):
				chosen_seq = pickFromFile_py(context,ITS2count, speciesDir + "/ITS2_only", speciesDir)
				if chosen_seq is not 0:
					species_counter += 1
					chosenSequences.append(chosen_seq)
					SeqIO.write(chosen_seq, total_ITS2_f, "fasta")
					total_its2_cnt += 1


	f_log.write("A total of %d sequences were chosen\n" %len(chosenSequences))
	f_log.write("Number of species =%d\n" %species_counter)
	f_log.write("Total seq count according to ITS type: combined=%d, its1=%d, its2=%d\n" %(total_combined_cnt,total_its1_cnt,total_its2_cnt))
	f_out = open(outputFile, 'w')
	for seq in chosenSequences:
		SeqIO.write(seq, f_out, "fasta")

	total_combined_f.close()
	total_ITS1_f.close()
	total_ITS2_f.close()

	return (total_its1_cnt,total_its2_cnt,total_combined_cnt)


def formatKeyWords(features_concat):

	logger.debug(features_concat)

	internal_transcribed = re.compile("internal transcribed spacer ", re.IGNORECASE)
	internal_trasncribed = re.compile("internal trasncribed spacer ", re.IGNORECASE)
	its_1 = re.compile("its 1", re.IGNORECASE)
	its_2 = re.compile("its 2", re.IGNORECASE)
	its1 = re.compile(" its1", re.IGNORECASE)
	its2 = re.compile(" its2", re.IGNORECASE)
	its = re.compile(" its ", re.IGNORECASE)

	features_concat_new = internal_transcribed.sub("ITS", features_concat)
	features_concat_new = internal_trasncribed.sub("ITS", features_concat_new)
	features_concat_new = its_1.sub("ITS1", features_concat_new)
	features_concat_new = its_2.sub("ITS2", features_concat_new)
	features_concat_new = its1.sub(" ITS1", features_concat_new)
	features_concat_new = its2.sub(" ITS2", features_concat_new)
	features_concat_new = its.sub(" ITS ", features_concat_new)

	logger.debug(features_concat_new)

	return features_concat_new


def splitITS_py(context,input, its1Output, its2Output, combinedOutput):

	its1Out = open (its1Output,'w')
	its2Out = open (its2Output,'w')
	combinedOut = open (combinedOutput,'w')
	logger.debug("Path for combined file:")
	logger.debug(combinedOutput)

	ITS1count=0
	ITS2count=0
	combinedCount=0

	seq_count=0
	#Find accession numbers of ITS seqs

	while seq_count < len(context.Accession_df):
		#logger.debug(str(context.Accession_df[seq_count]))
		if str(context.Accession_df[seq_count]) in context.its_accession_ids:
			taxon_fasta_str = str(context.taxon_Id_df[seq_count]) + '.fasta'
			if taxon_fasta_str in input:
				features_concat = context.definition_df[seq_count] + '|' + context.gene_name_location_df[seq_count] + '|' + \
								  context.note_df[seq_count] + '|' + context.mol_type_df[seq_count] + '|' + context.note_df[seq_count] + \
								  '|' + context.product_df[seq_count]
				desc = formatKeyWords(features_concat)

				#Need to get all the features data from features feild
				temp_its_accession = str(context.Accession_df[seq_count])
				if ('ITS1' in desc) and ('ITS2' in desc):
					combinedOut.write(context.desc_df[seq_count]+'\n')
					combinedOut.write(context.sequenceData_df[seq_count]+'\n')
					seq_len = len(context.sequenceData_df[seq_count])
					combinedCount+=1
					#Save Accession ITS type
					context.its_accession_vs_type[temp_its_accession] = 'combined'
					context.its_accession_vs_length[temp_its_accession] = seq_len

				elif ('ITS1' in desc) and ('ITS2' not in desc):
					its1Out.write(context.desc_df[seq_count] + '\n')
					its1Out.write(context.sequenceData_df[seq_count] + '\n')
					seq_len = len(context.sequenceData_df[seq_count])
					ITS1count += 1
					#Save Accession ITS type
					context.its_accession_vs_type[temp_its_accession] = 'its1'
					context.its_accession_vs_length[temp_its_accession] = seq_len

				elif ('ITS1' not in desc) and ('ITS2' in desc):
					its2Out.write(context.desc_df[seq_count] + '\n')
					its2Out.write(context.sequenceData_df[seq_count] + '\n')
					seq_len = len(context.sequenceData_df[seq_count])
					ITS2count += 1
					# Save Accession ITS type
					context.its_accession_vs_type[temp_its_accession] = 'its2'
					context.its_accession_vs_length[temp_its_accession]=seq_len

			seq_count += 1
		else:
			seq_count += 1
			continue

	return (ITS1count, ITS2count, combinedCount)



#Main ITS converted to python:

def main_ITS_py(context,OutDir, fasta, gene_db, scriptsDir, configFile, guidanceFlag, msa_software):

	f_mainITS_log = open(OutDir+'/MainITS.log','w')
	pickFromFastalog = OutDir+"/pickOneSeqFromFasta.log"
	pickFromMSAlog = OutDir+"/pickOneSeqFromMSA.log"
	its1fasta = OutDir+"/ITS1_only.fasta"
	its2fasta = OutDir+"/ITS2_only.fasta"
	itscombfasta = OutDir+"/combined.fasta"

	create_dir_if_not_exists(OutDir)

	f_mainITS_log.write("Filtering %s - each species will have at most one ITS seq of each type (ITS1/ITS2/combined) \n" %fasta)
	#--> Need to convert to python -> removed gbIndex since we use Database instead
	(ITS1count, ITS2count, combinedCount) = pickOneITSTypePerSpeciesFasta_py(context,fasta, OutDir, OutDir+"/oneITSTypePerSpecies.fasta", scriptsDir, pickFromFastalog)
	f_mainITS_log.write("ITS1count=%d, ITS2count=%d, combinedCount =%d, )" % (ITS1count, ITS2count, combinedCount))
	f_mainITS_log.write("Completed - pickOneITSTypePerSpeciesFasta_py\n")


	# separate the sequences, after they were filtered, to separate files that contain ITS1, ITS2 and ITS1+ITS2:
	##f_mainITS_log.write("Splitting filtered results by ITS type\n")
	#--> Need to convert to python ->
	##(ITS1count, ITS2count, combinedCount) = splitITS_py(context,OutDir+"/oneITSTypePerSpecies.fasta",its1fasta ,its2fasta, itscombfasta)
	##f_mainITS_log.write("Completed SplitITS: ITS1count=%d, ITS2count=%d, combinedCount =%d, )" % (ITS1count, ITS2count, combinedCount))

	# if there are no combined sequences in the genus, and the separated ITS1 and ITS2 sequences aren't aligned to each other,
	# so sequences from the same species should be appended and NOT merged
	append = 1
	if combinedCount > 0 :
		append = 0   # merge
	f_mainITS_log.write("append flag = %d (if 0-> merge,if 1-> append)" %append)


	if(ITS1count > 0 or ITS2count > 0 or combinedCount > 0):

		# Do MSA for the ITS seqs
		f_mainITS_log.write("Found ITS seqs - starting MSA for ITS\n")


		if (msa_software == 'ClustalOmega'):
			f_mainITS_log.write("MSA software -> ClustalOmega\n")
			MSAfileName = ITS_CLUSTALO_py(OutDir, ITS1count, ITS2count, combinedCount,its1fasta, its2fasta, itscombfasta,scriptsDir)
		else:
			f_mainITS_log.write("MSA software -> MAFFT\n")
			MSAfileName = ITS_MSA_py(OutDir, ITS1count, ITS2count, combinedCount,its1fasta, its2fasta, itscombfasta,scriptsDir)

		f_mainITS_log.write("After MSA - selecting a single ITS seq per species. MSA file: %s\n" % MSAfileName)
		pickOneSeqPerSpeciesMSA(context,MSAfileName, OutDir, OutDir+"/oneSeqPerSpecies.msa", scriptsDir, pickFromMSAlog,append)

		# Michal: NOT sure why we need this code? !!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
		#!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!
		find_all = re.findall(r"/combined\+sep\.msa/", MSAfileName)
		if(find_all):

			sep_fasta_f = ("%s/SEP_ITS1+ITS2.fasta" %OutDir)
			logger.debug("About to count number of seqs in %s\n" %sep_fasta_f)
			seq_sep_records = SeqIO.parse(sep_fasta_f, 'fasta')
			count_sep = len(seq_sep_records)
			logger.debug("Found %s seqs in %s\n" %(count_sep,sep_fasta_f))

			seq_comb_records = SeqIO.parse(itscombfasta, 'fasta')
			count_comb = len(seq_comb_records)
			logger.debug("Found %s seqs in %s\n" %(count_comb,itscombfasta))
			logger.debug("GUIDANCE Flag is set to: %s\n" %guidanceFlag)

			if (guidanceFlag == "True"):
				if (count_comb < 5 and count_sep < 5):
					logger.debug("NOT Calling GUIDANCE since there are only %d and %d sequences\n" %(count_comb,count_sep))
				else:
					logger.debug("GUIDANCE didn't run !!!!!!!!!!!!!!\n")
					# TO DO: calling GUIDANCE should be done with the correct files...
					##perform_filter_ITS_msa(context, OutDir + "/combined+sep.msa")
					#Gidance::runGuidance($itscombfasta, "$OutDir/SEP_ITS1+ITS2.fasta", "$OutDir/GuidnaceOutput", $configFile);
					#Gidance::checkGuidance($MSAfileName, $MSAfileName.".filtered_out", "$OutDir/GuidnaceOutput");

					# TO DO - use GUIDANCE results by overriding the MSA file with the filtered results
					#$MSAfileName = $MSAfileName.".filtered_out";

			else:
				logger.debug("Guidance Flag is set to False !!!")


		else:
			#if os.path.exists(OutDir + "/combined.msa"):
			#perform_filter_ITS_msa(context, OutDir + "/combined.fasta")
			#se:
			#TO DO - execute GUIDACE even in this case - it should be standatd GUIDANCE execution and not special like the above
			logger.debug("NOT Calling GUIDANCE since combined file doesn't exists\n")

	return



