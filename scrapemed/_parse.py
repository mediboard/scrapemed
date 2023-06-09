
"""
Parse module for grabbing metadata, text, tables, figures, etc. 
from XML trees representing PMC articles.

DTD for the XML should be NLM articleset 2.0. 
Otherwise the behavior here may not be as expected.

Middleman between the "scrape" module and the "paper" module for scrapemed.

"""

from typing import Text, List, Dict, Tuple
from typing import Union
import scrapemed.scrape as scrape
import lxml.etree as ET
from scrapemed.utils import basicBiMap
from scrapemed._text import TextParagraph
from scrapemed._text import TextSection
import pandas as pd

#-----------Custom Warnings & Exceptions for Parsing------------
class unexpectedMultipleMatchWarning(Warning):
    """
    Raised when one match expected, but multiple found.
    """
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

class unexpectedZeroMatchWarning(Warning):
    """
    Raised when one or more matches expected, and none found.
    """
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)

class badTextFormattingWarning(Warning):
    def __init__(self, message):
        self.message = message
    def __str__(self):
        return repr(self.message)
#-----------End Custom Warnings & Exceptions for Parsing------------

#--------------------GENERATE PAPER DICTIONARY GIVEN PMCID-------------------------------
def generate_paper_dict(pmcid:int, email:str, download:bool = False, validate:bool = True, verbose:bool = False)->dict:
    """TODO
    Wrapper that scrapes a PMC article specified by PMCID from the web (through scrape module),
    then parses the XML retrieved into a dictionary of useful values. 

    Middleman between scrape.py and paper.py.

    Paper objects in paper.py handle actual dictionary -> object conversion.
    """
    #DOWNLOAD XML TREE AND GET ROOT
    paper_tree = scrape.get_xml(pmcid=pmcid, email=email, download=download, validate=validate, verbose=verbose)
    root = paper_tree.getroot()

    #KEEP TRACK OF XREFS, TABLES, FIGURES IN BIMAP
    #(THIS WILL BE MODIFIED DURING TEXT RETRIEVAL WHEN HTML REF TAGS ARE SPLIT OUT)
    ref_map = basicBiMap()

    #STORE EXTRACTED INFO IN PAPER DICT
    paper_dict = {
        'Title': gather_title(root),
        'Authors': gather_authors(root),
        'Non-Author Contributors': gather_non_author_contributors(root),
        'Abstract': gather_abstract(root, ref_map),
        'Body': gather_body(root, ref_map),
        'Journal ID': gather_journal_id(root),
        'Journal Title': gather_journal_title(root),
        'ISSN': gather_issn(root),
        'Publisher Name': gather_publisher_name(root),
        'Publisher Location': gather_publisher_location(root),
        'Article ID': gather_article_id(root),
        'Article Type': gather_article_type(root),
        'Article Categories': gather_article_categories(root),
        'Subject': gather_subject(root),
        'Institution': gather_institution(root),
        'Institution ID': gather_institution_id(root),
        'Published Date': gather_published_date(root),
        'Volume': gather_volume(root),
        'Issue': gather_issue(root),
        'Permissions': gather_permissions(root),
        'Copyright Statement': gather_copyright_statement(root),
        'License': gather_license(root),
        'Funding Group': gather_funding_group(root),
        'Award Group': gather_award_group(root),
        'Funding Source': gather_funding_source(root),
        'Footnote': gather_footnote(root),
        'Acknowledgements': gather_acknowledgements(root),
        'Notes': gather_notes(root),
        'Reference List': gather_reference_list(root),
        'Ref Map': ref_map
        }

    return paper_dict

def gather_title(root: ET.Element)->str:
    """
    Grab the title of a PMC paper from its XML root.
    """
    matches = root.xpath('//article-meta/title-group/article-title/text()')
    if len(matches) > 1: 
        raise unexpectedMultipleMatchWarning("Warning! Multiple titles matched. Setting Paper.title to the first match.")
    title = matches[0]

    return title

def _get_contributor_tuples(root: ET.Element, contributors: List[ET.Element]) -> List[Tuple]:
    """
    Helper function to grab tuples of contributor information.

    Input:
    [root]: root of the XML tree to search
    [contributors]: list of lxml Element objects to grab information from

    Output:
    A list of tuples of contributor info in the form (contrib_type, first_name, last_name, address, affiliations).
    """
    contributor_tuples = []
    for contributor in contributors:
        contrib_type = contributor.get("contrib-type").capitalize()
        if contrib_type:
            contrib_type = contrib_type.strip()
        first_name = contributor.findtext(".//given-names")
        if first_name:
            first_name = first_name.strip()
        last_name = contributor.findtext(".//surname")
        if last_name:
            last_name = last_name.strip()
        address = contributor.findtext(".//address/email")
        if address:
            address = address.strip()
        affiliations = []
        aff_paths = contributor.xpath(".//xref[@ref-type='aff']")
        for aff in aff_paths:
            aff_id = aff.get('rid')
            aff_text = root.xpath(f"//contrib-group/aff[@id='{aff_id}']/text()[not(parent::label)]")
            if len(aff_text) > 1:
                raise Warning("Multiple affiliations with the same ID found. Check XML Formatting.")
            affiliation = f"{aff_id.strip()}: {aff_text[0].strip()}"
            affiliations.append(affiliation)
        contributor_tuples.append((contrib_type, first_name, last_name, address, affiliations))
    return contributor_tuples

def gather_authors(root: ET.Element)-> pd.DataFrame:
    """
    Gather authors and their emails and affiliations from a PMC XML.

    Returns a DataFrame of author info.
    """
    authors = root.xpath(".//contrib[@contrib-type='author']")
    if not authors:
        raise unexpectedZeroMatchWarning("Warning! Authors could not be matched")

    # Extract the first and last names of the authors and store them in a list
    author_tuples = _get_contributor_tuples(root=root, contributors=authors)

    authors_df = pd.DataFrame(author_tuples)
    authors_df.columns = ['Contributor_Type', 'First_Name', 'Last_Name', 'Email_Address', 'Affiliations']

    return authors_df

def gather_non_author_contributors(root: ET.Element) -> Union[str, pd.DataFrame]:
    """
    Gather non-author contributors from PMC XML.

    Returns either a string indicating none found, or a DataFrame of contributor info.
    """

    return_val = "No non-author contributors were found after parsing this paper."

    non_author_contributors = root.xpath(".//contrib[not(@contrib-type='author')]")
    if non_author_contributors:
        non_author_tuples = _get_contributor_tuples(root=root, contributors=non_author_contributors)
        non_authors_df = pd.DataFrame(non_author_tuples)
        non_authors_df.columns = ['Contributor_Type', 'First_Name', 'Last_Name', 'Email_Address', 'Affiliations']
        return_val = non_authors_df

    return return_val

def gather_abstract(root: ET.Element, ref_map:basicBiMap)->List[TextSection]:
    """
    Extract all abstract text sections from an xml, output as a list of TextSections. 
    """
    abstract = []

    #get abstract subtree from XML
    matches = root.xpath('//abstract')
    if len(matches) > 1: 
        raise unexpectedMultipleMatchWarning("Warning! Multiple abstracts matched. Filling in Paper.abstract with the first match.")
    abstract_root = matches[0]

    #iterate through abstract subtree and get dict of title, bodytext pairs
    for sec in abstract_root.iterchildren('sec'):
        abstract.append(TextSection(sec_root=sec, ref_map=ref_map))

    return abstract

def gather_body(root: ET.Element, ref_map:basicBiMap)->List[TextSection]:
    """
    Extract all body text sections from an xml, output as a list of TextSections. 
    """
    body = []

    #get abstract subtree from XML
    matches = root.xpath('//body')
    if len(matches) > 1: 
        raise unexpectedMultipleMatchWarning("Warning! Multiple 'body's matched. Filling in Paper.body with the first match.")
    body_root = matches[0]

    #iterate through abstract subtree and get dict of title, bodytext pairs
    for sec in body_root.iterchildren('sec'):
        body.append(TextSection(sec_root=sec, ref_map=ref_map))

    return body

def gather_journal_id(root: ET.Element) -> dict:
    """
    Gather Journal ID from PMC XML.
    """
    journal_ids = root.xpath("//journal-meta/journal-id")
    id_dict = {journal_id.get("journal-id-type"): journal_id.text for journal_id in journal_ids}

    return id_dict

def gather_journal_title(root: ET.Element) -> Union[List[str], str]:
    """
    Gather Journal Title from PMC XML.
    """
    return_val = None
    titles = []
    title_groups = root.xpath("//journal-meta/journal-title-group")
    for title_group in title_groups:
        titles.extend(title_group.getchildren())
    #might have multiple journals & journal titles
    if len(titles) > 1:
        return_val = [title.text for title in titles]
    else:
        return_val = titles[0].text
    return return_val

def gather_issn(root: ET.Element) -> dict:
    """
    Gather ISSN from PMC XML.
    """
    issns = root.xpath("//journal-meta/issn")
    issn_dict = {issn.get("pub-type"): issn.text for issn in issns}

    return issn_dict

def gather_publisher_name(root: ET.Element) -> Union[str, List[str]]:
    """
    Gather Publisher Name/s from PMC XML.
    """
    publisher_name_or_names = None
    publishers = root.xpath("//journal-meta/publisher/publisher-name")
    if len(publishers) == 1:
        publisher_name_or_names = publishers[0].text
    else:
        publisher_name_or_names = [publisher.text for publisher in publishers]
    return publisher_name_or_names

def gather_publisher_location(root: ET.Element) -> Union[str, List[str]]:
    """
    Gather Publisher Location/s from PMC XML.
    """
    publisher_loc_or_locs = None
    publisher_locs = root.xpath("//journal-meta/publisher/publisher-loc")
    if len(publisher_locs) == 1:
        publisher_loc_or_locs = publisher_locs[0].text
    else:
        publisher_loc_or_locs = [publisher_loc.text for publisher_loc in publisher_locs]
    return publisher_loc_or_locs

def gather_article_id(root: ET.Element) -> Dict[str, str]:
    """
    Gather Article IDs from PMC XML.
    """
    article_ids = root.xpath("//article-meta/article-id")
    id_dict = {article_id.get("pub-id-type"): article_id.text for article_id in article_ids}
    
    return id_dict

def gather_article_type(root: ET.Element) -> str:
    """
    Gather Article Type from PMC XML.
    """
    return None

def gather_article_categories(root: ET.Element) -> List[str]:
    """
    Gather Article Categories from PMC XML.
    """
    return []

def gather_subject(root: ET.Element) -> str:
    """
    Gather Subject from PMC XML.
    """
    return None

def gather_institution(root: ET.Element) -> str:
    """
    Gather Institution from PMC XML.
    """
    return None

def gather_institution_id(root: ET.Element) -> str:
    """
    Gather Institution ID from PMC XML.
    """
    return None

def gather_published_date(root: ET.Element) -> str:
    """
    Gather Published Date from PMC XML.
    """
    return None

def gather_volume(root: ET.Element) -> str:
    """
    Gather Volume from PMC XML.
    """
    return None

def gather_issue(root: ET.Element) -> str:
    """
    Gather Issue from PMC XML.
    """
    return None

def gather_permissions(root: ET.Element) -> List[str]:
    """
    Gather Permissions from PMC XML.
    """
    return []

def gather_copyright_statement(root: ET.Element) -> str:
    """
    Gather Copyright Statement from PMC XML.
    """
    return None

def gather_license(root: ET.Element) -> str:
    """
    Gather License from PMC XML.
    """
    return None

def gather_funding_group(root: ET.Element) -> str:
    """
    Gather Funding Group from PMC XML.
    """
    return None

def gather_award_group(root: ET.Element) -> List[str]:
    """
    Gather Award Group from PMC XML.
    """
    return []

def gather_funding_source(root: ET.Element) -> str:
    """
    Gather Funding Source from PMC XML.
    """
    return None


def gather_footnote(root: ET.Element) -> str:
    """
    Gather Footnote from PMC XML.
    """
    return None


def gather_acknowledgements(root: ET.Element) -> str:
    """
    Gather Acknowledgements from PMC XML.
    """
    return None


def gather_notes(root: ET.Element) -> str:
    """
    Gather Notes from PMC XML.
    """
    return None


def gather_reference_list(root: ET.Element) -> str:
    """
    Gather Reference List from PMC XML.
    """
    return None

#--------------------END GENERATE PAPER DICTIONARY GIVEN PMCID---------------------------