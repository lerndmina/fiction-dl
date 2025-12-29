####
#
# fiction-dl
# Copyright (C) (2020 - 2021) Benedykt Synakiewicz <dreamcobbler@outlook.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
####

#
#
#
# Imports.
#
#
#

# Application.

from fiction_dl.Concepts.Chapter import Chapter
from fiction_dl.Concepts.Extractor import Extractor
from fiction_dl.Utilities.HTML import StripHTML
from fiction_dl.Utilities import FlareSolverr
import fiction_dl.Configuration as Configuration

# Standard packages.

from datetime import datetime
import logging
import re
from typing import List, Optional

# Non-standard packages.

from bs4 import BeautifulSoup
from dreamy_utilities.Text import GetCurrentDate, Stringify
from dreamy_utilities.Web import GetHostname, GetSiteURL
from dreamy_utilities.WebSession import WebSession

#
#
#
# The class definition.
#
#
#

class ExtractorFFNet(Extractor):


    def __init__(self) -> None:

        ##
        #
        # The constructor.
        #
        ##

        super().__init__()

        self._webSession.EnableCloudscraper(True)
        self._chapterParserName = "html5lib"
        self._useFlareSolverr = Configuration.FlareSolverrPort is not None
        self._flareSolverrChecked = False
        self._flareSolverrAvailable = False

    def _CheckFlareSolverr(self) -> bool:

        ##
        #
        # Checks if FlareSolverr is available and warns if not.
        #
        # @return True if FlareSolverr is available, False otherwise.
        #
        ##

        if self._flareSolverrChecked:
            return self._flareSolverrAvailable

        self._flareSolverrChecked = True

        if not self._useFlareSolverr:
            print()
            print("! WARNING: FlareSolverr is not configured.")
            print("  FFN and FictionPress use Cloudflare protection and downloads will likely fail.")
            print("  To fix this, run FlareSolverr via Docker:")
            print("    docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest")
            print()
            self._flareSolverrAvailable = False
            return False

        # Check if FlareSolverr is actually responding
        self._flareSolverrAvailable = FlareSolverr.IsFlareSolverrRunning(Configuration.FlareSolverrPort)

        if not self._flareSolverrAvailable:
            print()
            print(f"! WARNING: FlareSolverr is not responding on port {Configuration.FlareSolverrPort}.")
            print("  FFN and FictionPress use Cloudflare protection and downloads will likely fail.")
            print("  Make sure FlareSolverr is running:")
            print("    docker run -d -p 8191:8191 ghcr.io/flaresolverr/flaresolverr:latest")
            print()

        return self._flareSolverrAvailable

    def _GetSoup(self, url: str, parserName: str = "html.parser") -> Optional[BeautifulSoup]:

        ##
        #
        # Gets BeautifulSoup for a URL, using FlareSolverr if configured.
        #
        # @param url        The URL to fetch.
        # @param parserName The parser to use for BeautifulSoup.
        #
        # @return BeautifulSoup object, or None on failure.
        #
        ##

        if self._useFlareSolverr:
            html = FlareSolverr.SolveChallenge(url, Configuration.FlareSolverrPort)
            if html:
                return BeautifulSoup(html, parserName)
            else:
                logging.warning(f"FlareSolverr failed for {url}, falling back to cloudscraper")
        
        return self._webSession.GetSoup(url, parserName)

    def ScanStory(self) -> bool:

        ##
        #
        # Scans the story: generates the list of chapter URLs and retrieves the
        # metadata. Overridden to use FlareSolverr when configured.
        #
        # @return **False** when the scan fails, **True** when it doesn't fail.
        #
        ##

        if self.Story is None:
            logging.error("The extractor isn't initialized.")
            return False

        # Check FlareSolverr availability and warn if not running
        self._CheckFlareSolverr()

        normalizedURL = self._GetNormalizedStoryURL(self.Story.Metadata.URL)

        soup = self._GetSoup(normalizedURL, self._chapterParserName)
        if not soup:
            logging.error(f'Failed to download tag soup: "{normalizedURL}".')
            return False

        return self._InternallyScanStory(normalizedURL, soup)

    def ExtractChapter(self, index: int) -> Optional[Chapter]:

        ##
        #
        # Extracts specific chapter. Overridden to use FlareSolverr when configured.
        #
        # @param index The index of the chapter to be extracted.
        #
        # @return **True** if the chapter is extracted correctly, **False** otherwise.
        #
        ##

        if index > len(self._chapterURLs):
            logging.error(
                f"Trying to extract chapter {index}. "
                f"Only {len(self._chapterURLs)} chapter(s) located. "
                f"The story supposedly has {self.Story.Metadata.ChapterCount} chapter(s)."
            )
            return None

        chapterURL = self._chapterURLs[index - 1]

        soup = self._GetSoup(chapterURL, self._chapterParserName)
        if not soup:
            logging.error(f'Failed to download tag soup: "{chapterURL}".')
            return None

        return self._InternallyExtractChapter(chapterURL, soup)

    def GetSupportedHostnames(self) -> List[str]:

        ##
        #
        # Returns a list of hostnames supposed to be supported by the extractor.
        #
        # @return A list of supported hostnames.
        #
        ##

        return [
            "fanfiction.net",
            "fictionpress.com"
        ]

    def ScanChannel(self, URL: str) -> Optional[List[str]]:

        ##
        #
        # Scans the channel: generates the list of story URLs.
        #
        # @return **None** when the scan fails, a list of story URLs when it doesn't fail.
        #
        ##

        if (not URL) or (GetHostname(URL) not in self.GetSupportedHostnames()):
            return None

        elif "/community/" in URL:
            return self._ScanCollection(URL)

        userIDMatch = re.search("/u/(\d+)", URL)
        if not userIDMatch:
            return None

        userID = userIDMatch.group(1)

        siteURL = GetSiteURL(URL)
        normalizedURL = f"{siteURL}/u/{userID}/"

        pageSoup = self._GetSoup(normalizedURL)
        if not pageSoup:
            return None

        storyIDs = []

        storyElements = pageSoup.find_all("div", {"class": "mystories"})
        for element in storyElements:

            linkElement = element.find("a", {"class": "stitle"})
            if (not linkElement) or (not linkElement.has_attr("href")):
                logging.error("Failed to retrieve story URL.")
                continue

            storyIDMatch = re.search("/s/(\d+)", linkElement["href"])
            if not storyIDMatch:
                logging.error("Failed to retrieve story ID from its URL.")
                continue

            storyID = storyIDMatch.group(1)
            storyIDs.append(storyID)

        storyURLs = [f"{siteURL}/s/{ID}/" for ID in storyIDs]
        return storyURLs

    def _ScanCollection(self, URL: str) -> Optional[List[str]]:

        ##
        #
        # Scans the channel: generates the list of story URLs.
        #
        # @return **None** when the scan fails, a list of story URLs when it doesn't fail.
        #
        ##

        # Retrieve collection name and generate a normalized URL.

        collectionNameAndIDMatch = re.search(
            "/community/([a-zA-Z0-9-]+)/(\d+)",
            URL
        )
        if not collectionNameAndIDMatch:
            logging.error("Failed to retrieve collection name/ID.")
            return None

        collectionName = collectionNameAndIDMatch.group(1)
        collectionID = collectionNameAndIDMatch.group(2)

        siteURL = GetSiteURL(URL)
        collectionURL = f"{siteURL}/community/{collectionName}/{collectionID}"
        normalizedURL = f"{collectionURL}/99/0/1/0/0/0/0/"

        # Download the first page.

        soup = self._GetSoup(normalizedURL)
        if not soup:
            logging.error(f"Failed to download page: \"{normalizedURL}\".")
            return None

        # Retrieve the number of pages.

        lastPageIndex = 1
        lastPageRelativeURL = None

        for elementCandidate in soup.select("center > a"):

            text = elementCandidate.get_text().strip()

            if "Last" == text:
                lastPageRelativeURL = elementCandidate["href"]
                break

        if lastPageRelativeURL:

            lastPageURLParts = lastPageRelativeURL.split("/")

            if len(lastPageURLParts) > 8:
                lastPageIndex = int(lastPageURLParts[-6])

        # Process each page of the collection.

        storyIDs = []

        for pageIndex in range(1, lastPageIndex + 1):

            pageURL = f"{collectionURL}/99/0/{pageIndex}/0/0/0/0/"
            soup = self._GetSoup(pageURL)
            if not soup:
                logging.error(f"Failed to download page: \"{pageURL}\".")
                return None

            for element in soup.select("div.z-list"):

                anchorElement = element.select_one("a.stitle")
                if (not anchorElement) or (not anchorElement.has_attr("href")):
                    logging.error("Failed to retrieve story URL.")
                    continue

                storyIDMatch = re.search("/s/(\d+)", anchorElement["href"])
                if not storyIDMatch:
                    logging.error("Failed to retrieve story ID from its URL.")
                    continue

                storyID = storyIDMatch.group(1)
                storyIDs.append(storyID)

        # Return.

        storyURLs = [f"{siteURL}/s/{ID}/" for ID in storyIDs]
        return storyURLs

    def _InternallyScanStory(
        self,
        URL: str,
        soup: Optional[BeautifulSoup]
    ) -> bool:

        ##
        #
        # Scans the story: generates the list of chapter URLs and retrieves the
        # metadata.
        #
        # @param URL  The URL of the story.
        # @param soup The tag soup.
        #
        # @return **False** when the scan fails, **True** when it doesn't fail.
        #
        ##

        # Extract metadata.

        headerElement = soup.find(id = "profile_top")
        if not headerElement:
            logging.error("Header element not found.")
            return False

        headerLines = headerElement.get_text().replace("Follow/Fav", "").split("\n")

        chapterCount = re.search("Chapters: (\d+)", headerLines[3])
        # If the story has just one chapter, this field won't be present.

        words = re.search("Words: ([\d,]+)", headerLines[3])
        if not words:
            logging.error("Word count field not found in header.")
            return False

        # Extract dates from span elements with data-xutime (Unix timestamps)
        # This is the most reliable method as it's locale-independent
        dateSpans = headerElement.find_all('span', attrs={'data-xutime': True})
        
        datePublishedTimestamp = None
        dateUpdatedTimestamp = None
        
        # FFN puts dates in spans with data-xutime attributes
        # The order is typically: Updated (if exists), then Published
        if len(dateSpans) >= 2:
            # Story has been updated: first span is Updated, second is Published
            dateUpdatedTimestamp = dateSpans[-2].get('data-xutime')
            datePublishedTimestamp = dateSpans[-1].get('data-xutime')
        elif len(dateSpans) == 1:
            # Story never updated: only Published exists
            datePublishedTimestamp = dateSpans[-1].get('data-xutime')
        
        # Convert timestamps to dates, or fall back to text parsing
        if datePublishedTimestamp:
            datePublished = self._TimestampToDate(datePublishedTimestamp)
        else:
            # Fallback: try to parse from text with multiple formats
            datePublished = self._ExtractDateFromText(headerLines[3], "Published")
        
        if not datePublished:
            logging.warning("Date published not found, using current date.")
            datePublished = GetCurrentDate()
        
        if dateUpdatedTimestamp:
            dateUpdated = self._TimestampToDate(dateUpdatedTimestamp)
        else:
            # Fallback: try to parse from text
            dateUpdated = self._ExtractDateFromText(headerLines[3], "Updated")

        # Set the metadata.

        self.Story.Metadata.Title = headerLines[0].strip()
        self.Story.Metadata.Author = headerLines[1][4:].strip() # Removes the "By: " part.
        self.Story.Metadata.Summary = StripHTML(headerLines[2]).strip()

        self.Story.Metadata.DatePublished = datePublished
        self.Story.Metadata.DateUpdated = dateUpdated if dateUpdated else datePublished

        self.Story.Metadata.ChapterCount = int(chapterCount.group(1)) if chapterCount else 1
        self.Story.Metadata.WordCount = int(words.group(1).replace(",", ""))

        # Retrieve chapter URLs.

        storyID = self._GetStoryID(self.Story.Metadata.URL)
        if not storyID:
            logging.error("Failed to retrieve story ID from URL.")
            return False

        baseURL = GetSiteURL(self.Story.Metadata.URL)
        for index in range(1, self.Story.Metadata.ChapterCount + 1):
            self._chapterURLs.append(f"{baseURL}/s/{storyID}/{index}/")

        # Return.

        return True

    def _InternallyExtractChapter(
        self,
        URL: str,
        soup: Optional[BeautifulSoup]
    ) -> Optional[Chapter]:

        ##
        #
        # Extracts specific chapter.
        #
        # @param URL  The URL of the page containing the chapter.
        # @param soup The tag soup of the page containing the chapter.
        #
        # @return **True** if the chapter is extracted correctly, **False** otherwise.
        #
        ##

        # Read the title.

        title = None

        if (selectedChapterElement := soup.find("option", {"selected": True})):
            title = selectedChapterElement.text.strip()

        if title and (titleMatch := re.search("\d+\. (.*)", title)):
            title = titleMatch.group(1)

        # Read the content.

        storyTextElement = soup.find(id = "storytext")
        if not storyTextElement:
            logging.error("Story text element not found.")
            return None

        # Create the Chapter and return it.

        return Chapter(
            title = title,
            content = Stringify(storyTextElement.encode_contents())
        )

    @staticmethod
    def _GetStoryID(URL: str) -> Optional[str]:

        if not URL:
            return None

        storyIDMatch = re.search("/s/(\d+)/", URL)
        if not storyIDMatch:
            return None

        return storyIDMatch.group(1)

    @staticmethod
    def _TimestampToDate(timestamp: str) -> Optional[str]:

        ##
        #
        # Converts a Unix timestamp to a date string.
        #
        # @param timestamp The Unix timestamp as a string.
        #
        # @return Date in YYYY-MM-DD format, or None on failure.
        #
        ##

        if not timestamp:
            return None

        try:
            ts = int(timestamp)
            return datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
        except (ValueError, OSError):
            return None

    @staticmethod
    def _ExtractDateFromText(text: str, dateType: str) -> Optional[str]:

        ##
        #
        # Extracts and parses a date from text, supporting multiple formats.
        #
        # @param text     The text containing the date.
        # @param dateType The type of date to look for ("Published" or "Updated").
        #
        # @return Date in YYYY-MM-DD format, or None on failure.
        #
        ##

        if not text:
            return None

        # Try multiple regex patterns for different date formats
        patterns = [
            # Numeric formats: m/d/yyyy, m/d/yy, m/d
            rf"{dateType}:\s*([\d]+/[\d]+(?:/[\d]+)?)",
            # Text formats: Mon DD, YYYY or Mon DD YYYY
            rf"{dateType}:\s*([A-Za-z]{{3}}\s+\d{{1,2}},?\s+\d{{4}})",
            # ISO format: YYYY-MM-DD
            rf"{dateType}:\s*(\d{{4}}-\d{{2}}-\d{{2}})",
        ]

        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                dateStr = match.group(1)
                parsed = ExtractorFFNet._ParseDateString(dateStr)
                if parsed:
                    return parsed

        return None

    @staticmethod
    def _ParseDateString(dateStr: str) -> Optional[str]:

        ##
        #
        # Parses a date string in various formats to YYYY-MM-DD.
        #
        # @param dateStr The date string to parse.
        #
        # @return Date in YYYY-MM-DD format, or None on failure.
        #
        ##

        if not dateStr:
            return None

        # List of formats to try
        formats = [
            "%m/%d/%Y",      # 3/31/2011
            "%m/%d/%y",      # 3/31/11
            "%m/%d",         # 3/31 (assume current year)
            "%b %d, %Y",     # Mar 31, 2011
            "%b %d %Y",      # Mar 31 2011
            "%B %d, %Y",     # March 31, 2011
            "%B %d %Y",      # March 31 2011
            "%Y-%m-%d",      # 2011-03-31
            "%d %b %Y",      # 31 Mar 2011
            "%d %B %Y",      # 31 March 2011
        ]

        dateStr = dateStr.strip()

        for fmt in formats:
            try:
                parsed = datetime.strptime(dateStr, fmt)
                # Handle short format without year
                if fmt == "%m/%d":
                    parsed = parsed.replace(year=datetime.now().year)
                return parsed.strftime("%Y-%m-%d")
            except ValueError:
                continue

        return None

    @staticmethod
    def _ReformatDate(date: str) -> Optional[str]:

        ##
        #
        # Legacy method for backward compatibility.
        # Reformats a date string to YYYY-MM-DD format.
        #
        # @param date The date string to reformat.
        #
        # @return Date in YYYY-MM-DD format, or current date on failure.
        #
        ##

        if not date:
            return None

        result = ExtractorFFNet._ParseDateString(date)
        return result if result else GetCurrentDate()