#!/usr/bin/env python2.6
# -*- coding: utf-8 -*-
"""
Open and modify Microsoft Word 2007 docx files (called 'OpenXML' and
'Office OpenXML' by Microsoft)

Part of Python's docx module - http://github.com/mikemaccana/python-docx
See LICENSE for licensing information.
"""

import logging, sys
from lxml import etree
try:
	from PIL import Image
except ImportError:
	import Image
import zipfile
import shutil
import re
import time
import os
from os.path import join

log = logging.getLogger(__name__)

# Record template directory's location which is just 'template' for a docx
# developer or 'site-packages/docx-template' if you have installed docx
template_dir = join(os.path.dirname(__file__), 'docx-template')  # installed
if not os.path.isdir(template_dir):
	template_dir = join(os.path.dirname(__file__), 'template')  # dev

# All Word prefixes / namespace matches used in document.xml & core.xml.
# LXML doesn't actually use prefixes (just the real namespace) , but these
# make it easier to copy Word output more easily.
nsprefixes = {
	'mo': 'http://schemas.microsoft.com/office/mac/office/2008/main',
	'o':  'urn:schemas-microsoft-com:office:office',
	've': 'http://schemas.openxmlformats.org/markup-compatibility/2006',
	# Text Content
	'w':   'http://schemas.openxmlformats.org/wordprocessingml/2006/main',
	'w10': 'urn:schemas-microsoft-com:office:word',
	'wne': 'http://schemas.microsoft.com/office/word/2006/wordml',
	# Drawing
	'a':   'http://schemas.openxmlformats.org/drawingml/2006/main',
	'm':   'http://schemas.openxmlformats.org/officeDocument/2006/math',
	'mv':  'urn:schemas-microsoft-com:mac:vml',
	'pic': 'http://schemas.openxmlformats.org/drawingml/2006/picture',
	'v':   'urn:schemas-microsoft-com:vml',
	'wp':  ('http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing'),
	# Properties (core and extended)
	'cp':  ('http://schemas.openxmlformats.org/package/2006/metadata/core-properties'),
	'dc':  'http://purl.org/dc/elements/1.1/',
	'ep':  ('http://schemas.openxmlformats.org/officeDocument/2006/extended-properties'),
	'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
	# Content Types
	'ct':  'http://schemas.openxmlformats.org/package/2006/content-types',
	# Package Relationships
	'r':  ('http://schemas.openxmlformats.org/officeDocument/2006/relationships'),
	'pr':  'http://schemas.openxmlformats.org/package/2006/relationships',
	# Dublin Core document properties
	'dcmitype': 'http://purl.org/dc/dcmitype/',
	'dcterms':  'http://purl.org/dc/terms/'}

def unzip_tmp(file, tmp_folder):
	zfile = zipfile.ZipFile(file)
	for name in zfile.namelist():
		(dirname, filename) = os.path.split(name)
		if filename == '':
			# directory
			if not os.path.exists(tmp_folder + '/' + dirname):
				os.mkdir(tmp_folder + '/' + dirname)
		else:
			# file
			fd = open(tmp_folder + '/' + name, 'wb')
			fd.write(zfile.read(name))
			fd.close()
	zfile.close()

def opendocx(file, tmp_folder):
	'''Open a docx file, return a document XML tree'''
	mydoc = zipfile.ZipFile(file)
	xmlcontent = mydoc.read('word/document.xml')
	document = etree.fromstring(xmlcontent)
	unzip_tmp(file, tmp_folder)
	return document

def newdocument():
	document = makeelement('document')
	document.append(makeelement('body'))
	return document

def makeelement(tagname, tagtext=None, nsprefix='w', attributes=None, attrnsprefix=None):
	'''Create an element & return it'''
	# Deal with list of nsprefix by making namespacemap
	namespacemap = None
	if isinstance(nsprefix, list):
		namespacemap = {}
		for prefix in nsprefix:
			namespacemap[prefix] = nsprefixes[prefix]
		# FIXME: rest of code below expects a single prefix
		nsprefix = nsprefix[0]
	if nsprefix:
		namespace = '{'+nsprefixes[nsprefix]+'}'
	else:
		# For when namespace = None
		namespace = ''
	newelement = etree.Element(namespace+tagname, nsmap=namespacemap)
	# Add attributes with namespaces
	if attributes:
		# If they haven't bothered setting attribute namespace, use an empty
		# string (equivalent of no namespace)
		if not attrnsprefix:
			# Quick hack: it seems every element that has a 'w' nsprefix for
			# its tag uses the same prefix for it's attributes
			if nsprefix == 'w':
				attributenamespace = namespace
			else:
				attributenamespace = ''
		else:
			attributenamespace = '{'+nsprefixes[attrnsprefix]+'}'

		for tagattribute in attributes:
			newelement.set(attributenamespace+tagattribute,
						   attributes[tagattribute])
	if tagtext:
		newelement.text = tagtext
	return newelement

def pagebreak(type='page', orient='portrait'):
	'''Insert a break, default 'page'.
	See http://openxmldeveloper.org/forums/thread/4075.aspx
	Return our page break element.'''
	# Need to enumerate different types of page breaks.
	validtypes = ['page', 'section']
	if type not in validtypes:
		tmpl = 'Page break style "%s" not implemented. Valid styles: %s.'
		raise ValueError(tmpl % (type, validtypes))
	pagebreak = makeelement('p')
	if type == 'page':
		run = makeelement('r')
		br = makeelement('br', attributes={'type': type})
		run.append(br)
		pagebreak.append(run)
	elif type == 'section':
		pPr = makeelement('pPr')
		sectPr = makeelement('sectPr')
		if orient == 'portrait':
			pgSz = makeelement('pgSz', attributes={'w': '12240', 'h': '15840'})
		elif orient == 'landscape':
			pgSz = makeelement('pgSz', attributes={'h': '12240', 'w': '15840', 'orient': 'landscape'})
		sectPr.append(pgSz)
		pPr.append(sectPr)
		pagebreak.append(pPr)
	return pagebreak

def linebreak():
	br = makeelement('br')
	return br

def paragraph(paratext, style='BodyText', breakbefore=False, jc='left', color='auto', size=None, ind=None):
	"""
	Return a new paragraph element containing *paratext*. The paragraph's
	default style is 'Body Text', but a new style may be set using the
	*style* parameter.

	@param string jc: Paragraph alignment, possible values:
					  left, center, right, both (justified), ...
					  see http://www.schemacentral.com/sc/ooxml/t-w_ST_Jc.html
					  for a full list

	If *paratext* is a list, add a run for each (text, char_format_str)
	2-tuple in the list. char_format_str is a string containing one or more
	of the characters 'b', 'i', or 'u', meaning bold, italic, and underline
	respectively. For example:

		paratext = [
			('some bold text', 'b'),
			('some normal text', ''),
			('some italic underlined text', 'iu')
		]
	"""
	# Make our elements
	paragraph = makeelement('p')

	if not isinstance(paratext, list):
		paratext = [(paratext, '')]
	text_tuples = []
	for pt in paratext:
		text, char_styles_str = (pt if isinstance(pt, (list, tuple))
								 else (pt, ''))
		text_elm = makeelement('t', tagtext=text)
		if len(text.strip()) < len(text):
			text_elm.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
		text_tuples.append([text_elm, char_styles_str])
	pPr = makeelement('pPr')
	pStyle = makeelement('pStyle', attributes={'val': style})
	pJc = makeelement('jc', attributes={'val': jc})
	pPr.append(pStyle)
	pPr.append(pJc)
	if ind:
		pPrInd = makeelement('ind', attributes={'left': str(ind)})
		pPr.append(pPrInd)
	# Add the text to the run, and the run to the paragraph
	paragraph.append(pPr)
	for text_elm, char_styles_str in text_tuples:
		run = makeelement('r')
		rPr = makeelement('rPr')
		# Apply styles
		if 'b' in char_styles_str:
			b = makeelement('b')
			rPr.append(b)
		if 'i' in char_styles_str:
			i = makeelement('i')
			rPr.append(i)
		if 'u' in char_styles_str:
			u = makeelement('u', attributes={'val': 'single'})
			rPr.append(u)
		rPrColor = makeelement('color', attributes={'val' : color})
		if size:
			rPrSize = makeelement('sz', attributes={'val' : str(int(size)*2)}) # times 2 because oxml uses half points
			rPr.append(rPrSize)
		rPr.append(rPrColor)
		run.append(rPr)
		# Insert lastRenderedPageBreak for assistive technologies like
		# document narrators to know when a page break occurred.
		if breakbefore:
			lastRenderedPageBreak = makeelement('lastRenderedPageBreak')
			run.append(lastRenderedPageBreak)
		run.append(text_elm)
		paragraph.append(run)
	# Return the combined paragraph
	return paragraph

def contenttypes():
	types = etree.fromstring(
		'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"></Types>')
	parts = {
		'/word/theme/theme1.xml': 'application/vnd.openxmlformats-officedocument.theme+xml',
		'/word/fontTable.xml':    'application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml',
		'/docProps/core.xml':     'application/vnd.openxmlformats-package.core-properties+xml',
		'/docProps/app.xml':	  'application/vnd.openxmlformats-officedocument.extended-properties+xml',
		'/word/document.xml':     'application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml',
		'/word/settings.xml':     'application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml',
		'/word/numbering.xml':    'application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml',
		'/word/styles.xml':       'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml',
		'/word/webSettings.xml':  'application/vnd.openxmlformats-officedocument.wordprocessingml.webSettings+xml'}
	for part in parts:
		types.append(makeelement('Override', nsprefix=None, attributes={'PartName': part, 'ContentType': parts[part]}))
	# Add support for filetypes
	filetypes = {
		'gif':  'image/gif',
		'jpeg': 'image/jpeg',
		'jpg':  'image/jpeg',
		'png':  'image/png',
		'rels': 'application/vnd.openxmlformats-package.relationships+xml',
		'xml':  'application/xml'
	}
	for extension in filetypes:
		attrs = {
			'Extension':   extension,
			'ContentType': filetypes[extension]
		}
		default_elm = makeelement('Default', nsprefix=None, attributes=attrs)
		types.append(default_elm)
	return types

def heading(headingtext, headinglevel, lang='en'):
	'''Make a new heading, return the heading element'''
	lmap = {'en': 'Heading', 'nl': 'Kop'}
	# Make our elements
	paragraph = makeelement('p')
	pr = makeelement('pPr')
	pStyle = makeelement(
		'pStyle', attributes={'val': lmap[lang]+str(headinglevel)})
	run = makeelement('r')
	text = makeelement('t', tagtext=headingtext)
	# Add the text the run, and the run to the paragraph
	pr.append(pStyle)
	run.append(text)
	paragraph.append(pr)
	paragraph.append(run)
	# Return the combined paragraph
	return paragraph

def caption(captiontext, lang='en'):
	'''Make a new caption, return the caption elemant'''
	lmap = {'en': 'Caption', 'nl': 'Bijschrift'}
	paragraph = makeelement('p')
	pr = makeelement('pPr')
	pStyle = makeelement('pStyle', attributes={'val': lmap[lang]})
	run = makeelement('r')
	text = makeelement('t', tagtext=captiontext)
	pr.append(pStyle)
	run.append(text)
	paragraph.append(pr)
	paragraph.append(run)
	return paragraph

def figureCaption(captiontext, lang='en'):
	'''Make a new caption for a figure, return the caption element'''
	lmap = {'en': 'Caption', 'nl': 'Bijschrift'}
	paragraph = makeelement('p')
	pr = makeelement('pPr')
	pStyle = makeelement('pStyle', attributes={'val': lmap[lang]})
	run1 = makeelement('r')
	text1 = makeelement('t', 'Afbeelding ')
	text1.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
	run1.append(text1)
	run2 = makeelement('r')
	text2 = makeelement('fldChar', attributes={'fldCharType': 'begin'})
	run2.append(text2)
	run3 = makeelement('r')
	text3 = makeelement('instrText', ' SEQ Figure \* ARABIC ')
	text3.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
	run3.append(text3)
	run4 = makeelement('r')
	text4 = makeelement('fldChar', attributes={'fldCharType': 'separate'})
	run4.append(text4)
	sequence_file = '/tmp/docx_seq'
	if os.path.isfile(sequence_file):
		f = open(sequence_file, 'r')
		sequence = int(f.readline())
		f.close()
	else:
		sequence = 1
	run5 = makeelement('r')
	text5 = makeelement('t', str(sequence))
	run5.append(text5)
	sequence += 1
	f = open(sequence_file, 'w')
	f.write(str(sequence))
	f.close()

	run6 = makeelement('r')
	text6 = makeelement('fldChar', attributes={'fldCharType': 'end'})
	run6.append(text6)
	run7 = makeelement('r')
	text7 = makeelement('t', ':')
	run7.append(text7)
	run8 = makeelement('r')
	text8 = makeelement('t', tagtext=' '+captiontext)
	text8.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
	run8.append(text8)
	pr.append(pStyle)
	paragraph.append(pr)
	paragraph.append(run1)
	paragraph.append(run2)
	paragraph.append(run3)
	paragraph.append(run4)
	paragraph.append(run5)
	paragraph.append(run6)
	paragraph.append(run7)
	paragraph.append(run8)
	return paragraph

def table(contents, heading=True, colw=None, cwunit='dxa', tblw=0, twunit='auto', borders={'all': {'color': 'auto', 'val': 'single', 'space': '0', 'sz': '4'}}, celstyle=None, headingFillColor='auto', firstColFillColor='auto'):
	"""
	Return a table element based on specified parameters

	@param list contents: A list of lists describing contents. Every item in
			      the list can be a string or a valid XML element
			      itself. It can also be a list. In that case all the
			      listed elements will be merged into the cell.
	@param bool heading:  Tells whether first line should be treated as
			      heading or not
	@param list colw:     list of integer column widths specified in wunitS.
	@param str  cwunit:   Unit used for column width:
							'pct'  : fiftieths of a percent
							'dxa'  : twentieths of a point
							'nil'  : no width
							'auto' : automagically determined
	@param int  tblw:     Table width
	@param int  twunit:   Unit used for table width. Same possible values as
						  cwunit.
	@param dict borders:  Dictionary defining table border. Supported keys
						  are: 'top', 'left', 'bottom', 'right',
						  'insideH', 'insideV', 'all'.
						  When specified, the 'all' key has precedence over
						  others. Each key must define a dict of border
						  attributes:
							color : The color of the border, in hex or
									'auto'
							space : The space, measured in points
							sz	: The size of the border, in eighths of
									a point
							val   : The style of the border, see
				http://www.schemacentral.com/sc/ooxml/t-w_ST_Border.htm
	@param list celstyle: Specify the style for each colum, list of dicts.
						  supported keys:
						  'align' : specify the alignment, see paragraph
									documentation.
	@param str  headingFillColor:  Specify a fill color for the first row of the table (if heading=True)
	@param str  firstColFillColor: Specify a fill color for the first column of the table
	@return lxml.etree:   Generated XML etree element
	"""
	table = makeelement('tbl')
	columns = len(contents[0])
	# Table properties
	tableprops = makeelement('tblPr')
	tablestyle = makeelement('tblStyle', attributes={'val': ''})
	tableprops.append(tablestyle)
	tablewidth = makeelement('tblW', attributes={'w': str(tblw), 'type': str(twunit)})
	tableprops.append(tablewidth)
	if len(borders.keys()):
		tableborders = makeelement('tblBorders')
		for b in ['top', 'left', 'bottom', 'right', 'insideH', 'insideV']:
			if b in borders.keys() or 'all' in borders.keys():
				k = 'all' if 'all' in borders.keys() else b
				attrs = {}
				for a in borders[k].keys():
					attrs[a] = unicode(borders[k][a])
				borderelem = makeelement(b, attributes=attrs)
				tableborders.append(borderelem)
		tableprops.append(tableborders)
	tablelook = makeelement('tblLook', attributes={'val': '0400'})
	tableprops.append(tablelook)
	table.append(tableprops)
	# Table Grid
	tablegrid = makeelement('tblGrid')
	for i in range(columns):
		attrs = {'w': str(colw[i]) if colw else '2390'}
		tablegrid.append(makeelement('gridCol', attributes=attrs))
	table.append(tablegrid)
	# Heading Row
	row = makeelement('tr')
	rowprops = makeelement('trPr')
	cnfStyle = makeelement('cnfStyle', attributes={'val': '000000100000'})
	rowprops.append(cnfStyle)
	row.append(rowprops)
	if heading:
		i = 0
		for heading in contents[0]:
			cell = makeelement('tc')
			# Cell properties
			cellprops = makeelement('tcPr')
			if colw:
				wattr = {'w': str(colw[i]), 'type': cwunit}
			else:
				wattr = {'w': '0', 'type': 'auto'}
			cellwidth = makeelement('tcW', attributes=wattr)
			cellstyle = makeelement('shd', attributes={'val': 'clear',
#								   'color': 'auto',
								   'color': 'FFFFFF',
#								   'fill': 'FFFFFF',
#								   'fill': 'ABDDFF'
								   'fill': headingFillColor
#								   'themeFill': 'text2',
#								   'themeFillTint': '99'
								   })
			cellprops.append(cellwidth)
			cellprops.append(cellstyle)
			cell.append(cellprops)
			# Paragraph (Content)
			if not isinstance(heading, (list, tuple)):
				heading = [heading]
			for h in heading:
				if isinstance(h, etree._Element):
					cell.append(h)
				else:
					cell.append(paragraph(h, jc='left', color='FFFFFF'))
			row.append(cell)
			i += 1
		table.append(row)
	# Contents Rows
	for contentrow in contents[1 if heading else 0:]:
		row = makeelement('tr')
		i = 0
		for content in contentrow:
			cell = makeelement('tc')
			# Properties
			cellprops = makeelement('tcPr')
			if colw:
				wattr = {'w': str(colw[i]), 'type': cwunit}
			else:
				wattr = {'w': '0', 'type': 'auto'}
			cellwidth = makeelement('tcW', attributes=wattr)
			cellprops.append(cellwidth)
			if i == 0:
				cellColor = makeelement('shd', attributes={'val': 'clear', 'color': 'auto', 'fill': firstColFillColor})
				cellprops.append(cellColor)
			cell.append(cellprops)
			# Paragraph (Content)
			if not isinstance(content, (list, tuple)):
				content = [content]
			for c in content:
				if isinstance(c, etree._Element):
					cell.append(c)
				else:
					if celstyle and 'align' in celstyle[i].keys():
						align = celstyle[i]['align']
					else:
						align = 'left'
					cell.append(paragraph(c, jc=align))
			row.append(cell)
			i += 1
		table.append(row)
	return table

def picture(relationshiplist, picname, picdescription, pixelwidth=None,	pixelheight=None, nochangeaspect=True, nochangearrowheads=True, jc='left'):
	"""
	Take a relationshiplist, picture file name, and return a paragraph
	containing the image and an updated relationshiplist.

	@param string jc: Paragraph alignment, possible values:
			  left, center, right, both (justified), ...
			  see http://www.schemacentral.com/sc/ooxml/t-w_ST_Jc.html
			  for a full list
	"""
	# http://openxmldeveloper.org/articles/462.aspx
	# Create an image. Size may be specified, otherwise it will based on the
	# pixel size of image. Return a paragraph containing the picture'''
	# Copy the file into the media dir
	media_dir = join(template_dir, 'word', 'media')
	if not os.path.isdir(media_dir):
		os.mkdir(media_dir)
	shutil.copyfile(picname, join(media_dir, os.path.basename(picname)))

	# Check if the user has specified a size
	if not pixelwidth and not pixelheight:
		# If not, get info from the picture itself
		pixelwidth, pixelheight = Image.open(picname).size[0:2]
	# If only pixelwidth is provided, calculate pixelheigth with aspect ratio
	if pixelwidth and not pixelheight:
		img_pixelwidth, img_pixelheight = Image.open(picname).size[0:2]
		aspect_ratio = float(pixelwidth) / float(img_pixelwidth)
		pixelheight = int(round(img_pixelheight * aspect_ratio))

	# OpenXML measures on-screen objects in English Metric Units
	# 1cm = 36000 EMUs
	emuperpixel = 12700
	width = str(pixelwidth * emuperpixel)
	height = str(pixelheight * emuperpixel)

	# Set relationship ID to the first available
	picid = '2'
	picrelid = 'rId'+str(len(relationshiplist)+1)
	relationshiplist.append([('http://schemas.openxmlformats.org/officeDocument/2006/relationships/image'), 'media/'+os.path.basename(picname)])

	# There are 3 main elements inside a picture
	# 1. The Blipfill - specifies how the image fills the picture area
	#	(stretch, tile, etc.)
	blipfill = makeelement('blipFill', nsprefix='pic')
	blipfill.append(makeelement('blip', nsprefix='a', attrnsprefix='r', attributes={'embed': picrelid}))
	stretch = makeelement('stretch', nsprefix='a')
	stretch.append(makeelement('fillRect', nsprefix='a'))
	blipfill.append(makeelement('srcRect', nsprefix='a'))
	blipfill.append(stretch)

	# 2. The non visual picture properties
	nvpicpr = makeelement('nvPicPr', nsprefix='pic')
	cnvpr = makeelement('cNvPr', nsprefix='pic', attributes={'id': '0', 'name': 'Picture 1', 'descr': os.path.basename(picname)})
	nvpicpr.append(cnvpr)
	cnvpicpr = makeelement('cNvPicPr', nsprefix='pic')
	cnvpicpr.append(makeelement('picLocks', nsprefix='a', attributes={'noChangeAspect': str(int(nochangeaspect)),	'noChangeArrowheads': str(int(nochangearrowheads))}))
	nvpicpr.append(cnvpicpr)

	# 3. The Shape properties
	sppr = makeelement('spPr', nsprefix='pic', attributes={'bwMode': 'auto'})
	xfrm = makeelement('xfrm', nsprefix='a')
	xfrm.append(makeelement('off', nsprefix='a', attributes={'x': '0', 'y': '0'}))
	xfrm.append(makeelement('ext', nsprefix='a', attributes={'cx': width, 'cy': height}))
	prstgeom = makeelement('prstGeom', nsprefix='a', attributes={'prst': 'rect'})
	prstgeom.append(makeelement('avLst', nsprefix='a'))
	sppr.append(xfrm)
	sppr.append(prstgeom)

	# Add our 3 parts to the picture element
	pic = makeelement('pic', nsprefix='pic')
	pic.append(nvpicpr)
	pic.append(blipfill)
	pic.append(sppr)

	# Now make the supporting elements
	# The following sequence is just: make element, then add its children
	graphicdata = makeelement('graphicData', nsprefix='a', attributes={'uri': ('http://schemas.openxmlformats.org/drawingml/2006/picture')})
	graphicdata.append(pic)
	graphic = makeelement('graphic', nsprefix='a')
	graphic.append(graphicdata)

	framelocks = makeelement('graphicFrameLocks', nsprefix='a', attributes={'noChangeAspect': '1'})
	framepr = makeelement('cNvGraphicFramePr', nsprefix='wp')
	framepr.append(framelocks)
	docpr = makeelement('docPr', nsprefix='wp', attributes={'id': picid, 'name': 'Picture 1', 'descr': picdescription})
	effectextent = makeelement('effectExtent', nsprefix='wp', attributes={'l': '25400', 't': '0', 'r': '0', 'b': '0'})
	extent = makeelement('extent', nsprefix='wp', attributes={'cx': width, 'cy': height})
	inline = makeelement('inline', attributes={'distT': "0", 'distB': "0", 'distL': "0", 'distR': "0"}, nsprefix='wp')
	inline.append(extent)
	inline.append(effectextent)
	inline.append(docpr)
	inline.append(framepr)
	inline.append(graphic)
	drawing = makeelement('drawing')
	drawing.append(inline)
	run = makeelement('r')
	run.append(drawing)
	pPr = makeelement('pPr')
	pJc = makeelement('jc', attributes={'val': jc})
	pPr.append(pJc)
	paragraph = makeelement('p')
	paragraph.append(pPr)
	paragraph.append(run)
	return relationshiplist, paragraph

def search(document, search):
	'''Search a document for a regex, return success / fail result'''
	result = False
	searchre = re.compile(search)
	for element in document.iter():
		if element.tag == '{%s}t' % nsprefixes['w']:  # t (text) elements
			if element.text:
				if searchre.search(element.text):
					result = True
	return result

def replace(document, search, replace):
	"""
	Replace all occurences of string with a different string, return updated
	document
	"""
	newdocument = document
	searchre = re.compile(search)
	for element in newdocument.iter():
		if element.tag == '{%s}t' % nsprefixes['w']:  # t (text) elements
			if element.text:
				if searchre.search(element.text):
					element.text = re.sub(search, replace, element.text)
	return newdocument

def clean(document):
	""" Perform misc cleaning operations on documents.
	    Returns cleaned document.
	"""
	newdocument = document

	# Clean empty text and r tags
	for t in ('t', 'r'):
		rmlist = []
		for element in newdocument.iter():
			if element.tag == '{%s}%s' % (nsprefixes['w'], t):
				if not element.text and not len(element):
					rmlist.append(element)
		for element in rmlist:
			element.getparent().remove(element)
	return newdocument

def findTypeParent(element, tag):
	""" Finds fist parent of element of the given type

	@param object element: etree element
	@param string the tag parent to search for

	@return object element: the found parent or None when not found
	"""

	p = element
	while True:
		p = p.getparent()
		if p.tag == tag:
			return p
	# Not found
	return None

def AdvSearch(document, search, bs=3):
	'''Return set of all regex matches

	This is an advanced version of python-docx.search() that takes into
	account blocks of <bs> elements at a time.

	What it does:
	It searches the entire document body for text blocks.
	Since the text to search could be spawned across multiple text blocks,
	we need to adopt some sort of algorithm to handle this situation.
	The smaller matching group of blocks (up to bs) is then adopted.
	If the matching group has more than one block, blocks other than first
	are cleared and all the replacement text is put on first block.

	Examples:
	original text blocks : [ 'Hel', 'lo,', ' world!' ]
	search : 'Hello,'
	output blocks : [ 'Hello,' ]

	original text blocks : [ 'Hel', 'lo', ' __', 'name', '__!' ]
	search : '(__[a-z]+__)'
	output blocks : [ '__name__' ]

	@param instance  document: The original document
	@param str	   search: The text to search for (regexp)
						  append, or a list of etree elements
	@param int	   bs: See above

	@return set	  All occurences of search string

	'''

	# Compile the search regexp
	searchre = re.compile(search)

	matches = []

	# Will match against searchels. Searchels is a list that contains last
	# n text elements found in the document. 1 < n < bs
	searchels = []

	for element in document.iter():
		if element.tag == '{%s}t' % nsprefixes['w']:  # t (text) elements
			if element.text:
				# Add this element to searchels
				searchels.append(element)
				if len(searchels) > bs:
					# Is searchels is too long, remove first elements
					searchels.pop(0)

				# Search all combinations, of searchels, starting from
				# smaller up to bigger ones
				# l = search lenght
				# s = search start
				# e = element IDs to merge
				found = False
				for l in range(1, len(searchels)+1):
					if found:
						break
					for s in range(len(searchels)):
						if found:
							break
						if s+l <= len(searchels):
							e = range(s, s+l)
							txtsearch = ''
							for k in e:
								txtsearch += searchels[k].text

							# Searcs for the text in the whole txtsearch
							match = searchre.search(txtsearch)
							if match:
								matches.append(match.group())
								found = True
	return set(matches)

def advReplace(document, search, replace, bs=3):
	"""
	Replace all occurences of string with a different string, return updated
	document

	This is a modified version of python-docx.replace() that takes into
	account blocks of <bs> elements at a time. The replace element can also
	be a string or an xml etree element.

	What it does:
	It searches the entire document body for text blocks.
	Then scan thos text blocks for replace.
	Since the text to search could be spawned across multiple text blocks,
	we need to adopt some sort of algorithm to handle this situation.
	The smaller matching group of blocks (up to bs) is then adopted.
	If the matching group has more than one block, blocks other than first
	are cleared and all the replacement text is put on first block.

	Examples:
	original text blocks : [ 'Hel', 'lo,', ' world!' ]
	search / replace: 'Hello,' / 'Hi!'
	output blocks : [ 'Hi!', '', ' world!' ]

	original text blocks : [ 'Hel', 'lo,', ' world!' ]
	search / replace: 'Hello, world' / 'Hi!'
	output blocks : [ 'Hi!!', '', '' ]

	original text blocks : [ 'Hel', 'lo,', ' world!' ]
	search / replace: 'Hel' / 'Hal'
	output blocks : [ 'Hal', 'lo,', ' world!' ]

	@param instance  document: The original document
	@param str	   search: The text to search for (regexp)
	@param mixed	 replace: The replacement text or lxml.etree element to
						 append, or a list of etree elements
	@param int	   bs: See above

	@return instance The document with replacement applied

	"""
	# Enables debug output
	DEBUG = False

	newdocument = document

	# Compile the search regexp
	searchre = re.compile(search)

	# Will match against searchels. Searchels is a list that contains last
	# n text elements found in the document. 1 < n < bs
	searchels = []

	for element in newdocument.iter():
		if element.tag == '{%s}t' % nsprefixes['w']:  # t (text) elements
			if element.text:
				# Add this element to searchels
				searchels.append(element)
				if len(searchels) > bs:
					# Is searchels is too long, remove first elements
					searchels.pop(0)

				# Search all combinations, of searchels, starting from
				# smaller up to bigger ones
				# l = search lenght
				# s = search start
				# e = element IDs to merge
				found = False
				for l in range(1, len(searchels)+1):
					if found:
						break
					#print "slen:", l
					for s in range(len(searchels)):
						if found:
							break
						if s+l <= len(searchels):
							e = range(s, s+l)
							#print "elems:", e
							txtsearch = ''
							for k in e:
								txtsearch += searchels[k].text

							# Searcs for the text in the whole txtsearch
							match = searchre.search(txtsearch)
							if match:
								found = True

								# I've found something :)
								if DEBUG:
									log.debug("Found element!")
									log.debug("Search regexp: %s", searchre.pattern)
									log.debug("Requested replacement: %s", replace)
									log.debug("Matched text: %s", txtsearch)
									log.debug("Matched text (splitted): %s", map(lambda i: i.text, searchels))
									log.debug("Matched at position: %s", match.start())
									log.debug("matched in elements: %s", e)
									if isinstance(replace, etree._Element):
										log.debug("Will replace with XML CODE")
									elif isinstance(replace(list, tuple)):
										log.debug("Will replace with LIST OF ELEMENTS")
									else:
										log.debug("Will replace with:", re.sub(search, replace, txtsearch))
								curlen = 0
								replaced = False
								for i in e:
									curlen += len(searchels[i].text)
									if curlen > match.start() and not replaced:
										# The match occurred in THIS element.
										# Puth in the whole replaced text
										if isinstance(replace, etree._Element):
											# Convert to a list and process
											# it later
											replace = [replace]
										if isinstance(replace, (list, tuple)):
											# I'm replacing with a list of
											# etree elements
											# clear the text in the tag and
											# append the element after the
											# parent paragraph
											# (because t elements cannot have
											# childs)
											p = findTypeParent(searchels[i], '{%s}p' % nsprefixes['w'])
											searchels[i].text = re.sub(search, '', txtsearch)
											insindex = p.getparent().index(p)+1
											for r in replace:
												p.getparent().insert(insindex, r)
												insindex += 1
										else:
											# Replacing with pure text
											searchels[i].text = re.sub(search, replace, txtsearch)
										replaced = True
										log.debug("Replacing in element #: %s", i)
									else:
										# Clears the other text elements
										searchels[i].text = ''
	return newdocument

def getdocumenttext(document):
	'''Return the raw text of a document, as a list of paragraphs.'''
	paratextlist = []
	# Compile a list of all paragraph (p) elements
	paralist = []
	for element in document.iter():
		# Find p (paragraph) elements
		if element.tag == '{'+nsprefixes['w']+'}p':
			paralist.append(element)
	# Since a single sentence might be spread over multiple text elements,
	# iterate through each paragraph, appending all text (t) children to that
	# paragraphs text.
	for para in paralist:
		paratext = u''
		# Loop through each paragraph
		for element in para.iter():
			# Find t (text) elements
			if element.tag == '{'+nsprefixes['w']+'}t':
				if element.text:
					paratext = paratext+element.text
			elif element.tag == '{'+nsprefixes['w']+'}tab':
				paratext = paratext + '\t'
		# Add our completed paragraph text to the list of paragraph text
		if not len(paratext) == 0:
			paratextlist.append(paratext)
	return paratextlist

def coreproperties(title, subject, creator, keywords, lastmodifiedby=None):
	"""
	Create core properties (common document properties referred to in the
	'Dublin Core' specification). See appproperties() for other stuff.
	"""
	coreprops = makeelement('coreProperties', nsprefix='cp')
	coreprops.append(makeelement('title', tagtext=title, nsprefix='dc'))
	coreprops.append(makeelement('subject', tagtext=subject, nsprefix='dc'))
	coreprops.append(makeelement('creator', tagtext=creator, nsprefix='dc'))
	coreprops.append(makeelement('keywords', tagtext=','.join(keywords), nsprefix='cp'))
	if not lastmodifiedby:
		lastmodifiedby = creator
	coreprops.append(makeelement('lastModifiedBy', tagtext=lastmodifiedby, nsprefix='cp'))
	coreprops.append(makeelement('revision', tagtext='1', nsprefix='cp'))
	coreprops.append(makeelement('category', tagtext='Examples', nsprefix='cp'))
	coreprops.append(makeelement('description', tagtext='Examples', nsprefix='dc'))
	currenttime = time.strftime('%Y-%m-%dT%H:%M:%SZ')
	# Document creation and modify times
	# Prob here: we have an attribute who name uses one namespace, and that
	# attribute's value uses another namespace.
	# We're creating the element from a string as a workaround...
	for doctime in ['created', 'modified']:
		elm_str = (
			'<dcterms:%s xmlns:xsi="http://www.w3.org/2001/XMLSchema-instanc'
			'e" xmlns:dcterms="http://purl.org/dc/terms/" xsi:type="dcterms:'
			'W3CDTF">%s</dcterms:%s>'
		) % (doctime, currenttime, doctime)
		coreprops.append(etree.fromstring(elm_str))
	return coreprops

def appproperties():
	"""
	Create app-specific properties. See docproperties() for more common
	document properties.

	"""
	appprops = makeelement('Properties', nsprefix='ep')
	appprops = etree.fromstring(
		'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties x'
		'mlns="http://schemas.openxmlformats.org/officeDocument/2006/extended'
		'-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocum'
		'ent/2006/docPropsVTypes"></Properties>')
	props =\
		{'Template':		 'Normal.dotm',
		 'TotalTime':		 '6',
		 'Pages':		 '1',
		 'Words':		 '83',
		 'Characters':		 '475',
		 'Application':		 'Microsoft Word 12.0.0',
		 'DocSecurity':		 '0',
		 'Lines':		 '12',
		 'Paragraphs':		 '8',
		 'ScaleCrop':		 'false',
		 'LinksUpToDate':	 'false',
		 'CharactersWithSpaces': '583',
		 'SharedDoc':		 'false',
		 'HyperlinksChanged':	 'false',
		 'AppVersion':		 '12.0000'}
	for prop in props:
		appprops.append(makeelement(prop, tagtext=props[prop], nsprefix=None))
	return appprops

def websettings():
	'''Generate websettings'''
	web = makeelement('webSettings')
	web.append(makeelement('allowPNG'))
	web.append(makeelement('doNotSaveAsSingleFile'))
	return web

def relationshiplist(fromFile, tmp_folder):
	if not fromFile:
		# Create relationshiplist from scratch
		relationshiplist =\
			[['http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering', 'numbering.xml'],
			 ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles', 'styles.xml'],
			 ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings', 'settings.xml'],
			 ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/webSettings', 'webSettings.xml'],
			 ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable', 'fontTable.xml'],
			 ['http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme', 'theme/theme1.xml']]
	else:
		# Get relationshiplist from template "fromFile"
		tmp_relationshiplist = []
		import xml.etree.ElementTree as ET
		tree = ET.parse(tmp_folder + '/word/_rels/document.xml.rels')
		root = tree.getroot()
		for child in root:
			id = child.get('Id').split('Id')[1] # Add id for sorting purposes
			item = [int(id), child.get('Type'), child.get('Target')]
			tmp_relationshiplist.append(item)
		tmp_relationshiplist.sort()
		relationshiplist = []
		for relationship in tmp_relationshiplist:
			item = [relationship[1], relationship[2]]
			relationshiplist.append(item)
	return relationshiplist

def wordrelationships(relationshiplist):
	'''Generate a Word relationships file'''
	# Default list of relationships
	# FIXME: using string hack instead of making element
	#relationships = makeelement('Relationships', nsprefix='pr')
	relationships = etree.fromstring(
		'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>')
	count = 0
	for relationship in relationshiplist:
		# Relationship IDs (rId) start at 1.
		rel_elm = makeelement('Relationship', nsprefix=None, attributes={'Id':	 'rId'+str(count+1), 'Type':   relationship[0], 'Target': relationship[1]})
		relationships.append(rel_elm)
		count += 1
	return relationships

def savedocx(document, coreprops=None, appprops=None, contenttypes=None, websettings=None, wordrelationships=None, output=None, template=None, tmp_folder=None):
	'''Save a modified document'''
	assert os.path.isdir(template_dir)
	docxfile = zipfile.ZipFile(output, mode='w', compression=zipfile.ZIP_DEFLATED)

	# Move to the template data path
	prev_dir = os.path.abspath('.')  # save previous working dir
	if not template:
		os.chdir(template_dir)
		# Serialize our trees into out zip file
		treesandfiles = {document:          'word/document.xml',
				 coreprops:         'docProps/core.xml',
				 appprops:          'docProps/app.xml',
				 contenttypes:      '[Content_Types].xml',
				 websettings:       'word/webSettings.xml',
				 wordrelationships: 'word/_rels/document.xml.rels'}
	else:
		os.chdir(tmp_folder)
		os.remove('word/document.xml')
		os.remove('docProps/core.xml')
		os.remove('word/_rels/document.xml.rels')
		treesandfiles = {document:          'word/document.xml',
				 coreprops:	    'docProps/core.xml',
				 wordrelationships: 'word/_rels/document.xml.rels'}

	for tree in treesandfiles:
		log.info('Saving: %s' % treesandfiles[tree])
		treestring = etree.tostring(tree, pretty_print=True)
		docxfile.writestr(treesandfiles[tree], treestring)

	# Add & compress support files
	files_to_ignore = ['.DS_Store']  # nuisance from some os's
	for dirpath, dirnames, filenames in os.walk('.'):
		for filename in filenames:
			if filename in files_to_ignore:
				continue
			templatefile = join(dirpath, filename)
			archivename = templatefile[2:]
			log.info('Saving: %s', archivename)
			docxfile.write(templatefile, archivename)
	log.info('Saved new file to: %r', output)
	docxfile.close()
	os.chdir(prev_dir)  # restore previous working dir
	return
