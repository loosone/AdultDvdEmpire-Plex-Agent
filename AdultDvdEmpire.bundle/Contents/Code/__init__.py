# AdultDvdEmpire
import re, types, traceback
import Queue
from __builtin__ import *
from lxml.etree import tostring

# URLS
VERSION_NO = '1.2017.10.15.1'
ADE_BASE_URL = 'http://www.adultdvdempire.com/'
ADE_MOVIE_INFO = ADE_BASE_URL + '%s'
ADE_SEARCH_URL = ADE_BASE_URL + 'allsearch/search?q=%s'
ADE_STAR_PHOTO = 'https://imgs1cdn.adultempire.com/actors/%s.jpg'
ADE_RATING_IMAGE = 'https://thrifty-production.s3.amazonaws.com/uploads/store/logo/9d4dd375-3d24-4234-a05f-1bc1a00d9887/adultempirecom.png'

REQUEST_DELAY = 0       # Delay used when requesting HTML, may be good to have to prevent being banned from the site

INITIAL_SCORE = 100     # Starting value for score before deductions are taken.
GOOD_SCORE = 98         # Score required to short-circuit matching and stop searching.
IGNORE_SCORE = 45       # Any score lower than this will be ignored.

THREAD_MAX = 20

def Start():
    HTTP.CacheTime = CACHE_1WEEK
    HTTP.Headers['User-agent'] = 'Mozilla/4.0 (compatible; MSIE 8.0; Windows NT 6.2; Trident/4.0; SLCC2; .NET CLR 2.0.50727; .NET CLR 3.5.30729; .NET CLR 3.0.30729; Media Center PC 6.0)'
    HTTP.Headers['Accept-Encoding'] = 'gzip'

class AdultDvdEmpire(Agent.Movies):
    name = 'AdultDvdEmpire'
    languages = [Locale.Language.NoLanguage]
    primary_provider = True
    accepts_from = ['com.plexapp.agents.localmedia']

    prev_search_provider = 0

    def Log(self, message, *args):
        if Prefs['debug']:
            Log(message, *args)

    def getDateFromString(self, string):
        try:
            return Datetime.ParseDate(string).date()
        except:
            return None

    def getStringContentFromXPath(self, source, query):
        return source.xpath(query)[0].text

    def getAnchorUrlFromXPath(self, source, query):
        anchor = source.xpath(query)

        if len(anchor) == 0:
            return None

        return anchor[0].get('href')

    def getImageUrlFromXPath(self, source, query):
        img = source.xpath(query)

        if len(img) == 0:
            return None

        return img[0].get('src')

    def findDateInTitle(self, title):
        result = re.search(r'(\d+-\d+-\d+)', title)
        if result is not None:
            return Datetime.ParseDate(result.group(0)).date()
        return None

    def doSearch(self, url):
        html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)
        found = []
        for r in html.xpath('//div[@class="row list-view-item  "]'):
            date = None
            try:
                date = self.getDateFromString(r.xpath('.//small[text()="released"]/parent::span/text()')[0].replace('"', '').strip())
            except:
                pass
            if date is None:
                try:
                    date = self.getDateFromString(r.xpath('./div[2]/h3/small[2]/text()')[0].replace('(', '').replace(')', '').strip())
                except:
                    pass
            title = r.xpath('.//a[@title]')[0].get('title')
            murl = ADE_BASE_URL + self.getAnchorUrlFromXPath(r, './/a[@title]')
            thumb = self.getImageUrlFromXPath(r, './/a[@title]/img')
            found.append({'url': murl, 'title': title, 'date': date, 'thumb': thumb})
        return found

    def search(self, results, media, lang, manual=False):
        if media.name.isdigit():

            self.Log('Media.name is numeric')
            # Make url
            url = ADE_MOVIE_INFO % media.name
            # Fetch HTML
            html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)
            # Set the result
            results.Append(MetadataSearchResult(id = media.name, name = self.getStringContentFromXPath(html, '//h1'), score = '100', lang = lang))

        yearFromNamePattern = r'\(\d{4}\)'
        yearFromName = re.search(yearFromNamePattern, media.name)
        if not media.year and yearFromName is not None:
            media.year = yearFromName.group(0)[1:-1]
            media.name = re.sub(yearFromNamePattern, '', media.name).strip()
            self.Log('Found the year %s in the name "%s". Using it to narrow search.', media.year, media.name)

        # Clean up year.
        if media.year:
            searchYear = u' (' + safe_unicode(media.year) + u')'
        else:
            searchYear = u''

        # Normalize the name
        normalizedName = String.StripDiacritics(media.name)
        if len(normalizedName) == 0:
            normalizedName = media.name

        # Make the URL
        searchUrl = ADE_SEARCH_URL % (String.Quote((normalizedName).encode('utf-8'), usePlus=True))
        found = self.doSearch(searchUrl)
        found2 = media.name.lstrip('0123456789')
        if normalizedName != found2:
            searchUrl = ADE_SEARCH_URL % (String.Quote((found2).encode('utf-8'), usePlus=True))
            found.extend(self.doSearch(searchUrl))

        # Write search result status to log
        if len(found) == 0:
            self.Log('No results found for query "%s"%s', normalizedName, searchYear)
            return
        else:
            self.Log('Found %s result(s) for query "%s"%s', len(found), normalizedName, searchYear)
            i = 1
            for f in found:
                self.Log('    %s. %s [%s] (%s) {%s}', i, f['title'], f['url'], str(f['date']), f['thumb'])
                i += 1

        self.Log('-----------------------------------------------------------------------')
        # Walk the found items and gather extended information
        info = []
        i = 1
        for f in found:
            url = f['url']
            title = f['title']
            thumb = f['thumb']
            date = f['date']
            year = ''

            # Get the id
            itemId = url.split('/')[-2]

            if len(itemId) == 0:
                continue
            if date is not None:
                year = date.year
            else:
                date = ''

            # Evaluate the score
            scorebase1 = media.name
            scorebase2 = title.encode('utf-8')

            if media.year:
                scorebase1 += ' (' + media.year + ')'
                scorebase2 += ' (' + str(year) + ')'

            score = INITIAL_SCORE - Util.LevenshteinDistance(scorebase1, scorebase2)

            if score >= IGNORE_SCORE:
                info.append({'id': itemId, 'title': title, 'year': year, 'date': date, 'score': score, 'thumb': thumb})
            else:
                self.Log('# Score is below ignore boundary (%s)... Skipping!', IGNORE_SCORE)

            if i != len(found):
                self.Log('-----------------------------------------------------------------------')

            i += 1

        info = sorted(info, key=lambda inf: inf['score'], reverse=True)

        i = 1
        for r in info:
            self.Log('    [%s]    %s. %s (%s) {%s} [%s]', r['score'], i, r['title'], r['year'], r['id'], r['thumb'])
            results.Append(MetadataSearchResult(id = r['id'], name = r['title'] + ' [' + str(r['date']) + ']', score = r['score'], thumb = r['thumb'], lang = lang))

            # If there are more than one result, and this one has a score that is >= GOOD SCORE, then ignore the rest of the results
            if not manual and len(info) > 1 and r['score'] >= GOOD_SCORE:
                self.Log('            *** The score for these results are great, so we will use them, and ignore the rest. ***')
                break
            i += 1

    def update(self, metadata, media, lang, force=False):
        self.Log('***** UPDATING "%s" ID: %s - ADE v.%s *****', media.title, metadata.id, VERSION_NO)

        # Make url
        url = ADE_MOVIE_INFO % metadata.id

        try:
            # Fetch HTML
            html = HTML.ElementFromURL(url, sleep=REQUEST_DELAY)

            # Set tagline to URL
            metadata.tagline = url

            # Get the title
            metadata.title = html.xpath('//h1')[0].text.strip()

            # Set dates
            releaseDate = None
            releaseYear = None
            try:
               releaseDate = self.getDateFromString(html.xpath('//small[text()="Released:"]/parent::li/text()')[0].replace('"', '').strip())
            except:
                pass
            releaseYear = self.getDateFromString(html.xpath('//small[text()="Production Year:"]/parent::li/text()')[0].replace('"', '').strip())
            if releaseDate is not None:
                metadata.originally_available_at = releaseDate
            else:
                metadata.originally_available_at = releaseYear.date
            metadata.year = releaseYear.year
            metadata.content_rating = 'Adult'
        except Exception, e:
            Log.Error('Error obtaining basic data for item with id %s (%s) [%s] ', metadata.id, url, e.message)

        try:
            #Get ratings
            metadata.rating_image = 'image:url(' + ADE_RATING_IMAGE + ')'
            rating = float(html.xpath('//h2[contains(text(),"Average Rating")]')[0].text.strip('\n').strip('Average Rating '))
            metadata.rating = rating / 5 * 10
            #metadata.audience_rating_image
        except Exception, e:
            Log.Error('Error obtaining ratings data for item with id %s (%s) [%s]', metadata.id, url, e.message)
            
        # Set the summary
        try:
            paragraph = html.xpath('//h4[@class="spacing-bottom text-dark synopsis"]/parent::div')
            summary = paragraph[0].text_content().strip('\n').strip()
            metadata.summary = summary
        except Exception, e:
            Log.Error('Error obtaining summary data for item with id %s (%s) [%s]', metadata.id, url, e.message)

        # Set the studio
        studio = html.xpath('//small[text()="Studio: "]/parent::li/a')
        try:
            metadata.studio = studio[0].text
        except Exception, e:
            Log.Error('Error obtaining studio data for item with id %s (%s) [%s]', metadata.id, url, e.message)

        # Set director
        directorElem = html.xpath('//small[text()="Director"]/parent::li/a')
        directorName = None
        try:
            directorName = directorElem[0].text.strip('\n').strip()
            metadata.directors.clear()
            director = metadata.directors.new()
            director.name = directorName
        except Exception, e:
            Log.Error('Error obtaining director data for item with id %s (%s) [%s] ', metadata.id, url, e.message)

        # Set series and add to collections
        metadata.collections.clear()
        series = html.xpath('//a[@label="Series"]')
        try:
            metadata.collections.add(series[0].text.split('"')[1])
        except:
            pass

        # Add the genres
        try:
            metadata.genres.clear()
            genres = html.xpath('//a[@label="Category"]/parent::li')
            for genre in genres:
               metadata.genres.add(genre.text_content().strip('\n').strip())
        except Exception, e:
            Log.Error('Error obtaining genres data for item with id %s (%s) [%s]', metadata.id, url, e.message)

        # Add the performers
        try:
            metadata.roles.clear()
            for performer in html.xpath('//a[@name="cast"]/parent::div/ul/li'):
                performerName = self.getStringContentFromXPath(performer, './a').strip('\n').strip()
                # Log.Debug('Performer: %s', str(dir(metadata.directors[0])))
                if directorName is None or performerName.startswith(directorName) is False:
                    role = metadata.roles.new()
                    role.name = performerName
                    # Get the url for performer photo
                    role.photo = ADE_STAR_PHOTO % performer.xpath('./a')[0].get('href').split('/')[1]
        except Exception, e:
            Log.Error('Error obtaining performers data for item with id %s (%s) [%s]', metadata.id, url, e.message)

        # Get posters and fan art.
        self.getImages(url, html, metadata, force)

    def hasProxy(self):
        return Prefs['imageproxyurl'] is not None

    def makeProxyUrl(self, url, referer):
        return Prefs['imageproxyurl'] + ('?url=%s&referer=%s' % (url, referer))

    def worker(self, queue, stoprequest):
        while not stoprequest.isSet():
            try:
                func, args, kargs = queue.get(True, 0.05)
                try: func(*args, **kargs)
                except Exception, e: self.Log(e)
                queue.task_done()
            except Queue.Empty:
                continue

    def addTask(self, queue, func, *args, **kargs):
        queue.put((func, args, kargs))

    def getImages(self, url, mainHtml, metadata, force):
        queue = Queue.Queue(THREAD_MAX)
        stoprequest = Thread.Event()
        for _ in range(THREAD_MAX): Thread.Create(self.worker, self, queue, stoprequest)

        results = []

        self.addTask(queue, self.getPosters, url, mainHtml, metadata, results, force, queue)

        scene_image_max = 20
        try:
            scene_image_max = int(Prefs['sceneimg'])
        except:
            Log.Error('Unable to parse the Scene image count setting as an integer.')

        if scene_image_max >= 0:
            for i, scene in enumerate(mainHtml.xpath('//div[@class="row scene-row"]')):
                sceneName = self.getStringContentFromXPath(scene, '//h3')
                scenedId = scene.xpath('.//a[@data-sceneid]')[0].get('data-sceneid')
                self.addTask(queue, self.getSceneImages, i, mainHtml, scenedId, metadata, scene_image_max, results, force, queue)

        queue.join()
        stoprequest.set()

        from operator import itemgetter
        for i, r in enumerate(sorted(results, key=itemgetter('scene', 'index'))):
            if r['isPreview']:
                proxy = Proxy.Preview(r['image'], sort_order=i+1)
            else:
                proxy = Proxy.Media(r['image'], sort_order=i+1)

            if r['scene'] > -1:
                metadata.art[r['url']] = proxy
            else:
                #self.Log('added poster %s (%s)', r['url'], i)
                metadata.posters[r['url']] = proxy

    def getPosters(self, url, mainHtml, metadata, results, force, queue):
        i = 0
        #get full size posters
        #for poster in mainHtml.xpath('//a[@data-lightbox="covers"]/@href'):
        imageBase = mainHtml.xpath('//div[@id="Boxcover"]//img/@src')[0].rsplit('/', 1)[-2]
        front = imageBase + '/' + metadata.id + 'h.jpg'
        back = imageBase + '/' + metadata.id + 'bh.jpg'
        self.addTask(queue, self.downloadImage, front, front, url, False, i, -1, results)
        i = i + 1
        self.addTask(queue, self.downloadImage, back, back, url, False, i, -1, results)
        i = i + 1
        #Always get the lower-res poster from the main page that tends to be just the front cover.  This is close to 100% reliable
        #imageUrl = self.getImageUrlFromXPath(mainHtml, '//img[@alt="Cover"]')
        #self.addTask(queue, self.downloadImage, imageUrl, imageUrl, url, False, i, -1, results)


    def getSceneImages(self, sceneIndex, page, sceneId, metadata, sceneImgMax, result, force, queue):
        imgCount = 0
        images = sceneHtml.xpath('//a[img[contains(@alt,"image")]]/img')
        if images is not None and len(images) > 0:
            firstImage = images[0].get('src')
            thumbPatternSearch = re.search(r'(th\w*)/', firstImage)
            thumbPattern = None
            if thumbPatternSearch is not None:
                thumbPattern = thumbPatternSearch.group(1)
            #get viewer page
            firstViewerPageUrl = images[0].xpath('..')[0].get('href')
            html = HTML.ElementFromURL(firstViewerPageUrl, sleep=REQUEST_DELAY)

            imageCount = None
            imageCountSearch = re.search(r'Image \d+ of (\d+)', html.text_content())
            if imageCountSearch is not None:
                imageCount = int(imageCountSearch.group(1))
            else:
                # No thumbs were found on the page, which seems to be the case for some scenes where there are only 4 images
                # so let's just pretend we found thumbs
                imageCount = 4

            # plex silently dies or kills this off if it downloads too much stuff, especially if there are errors. have to manually limit numbers of images for now
            # workaround!!!
            if imageCount > 3:
                imageCount = 3

            # Find the actual first image on the viewer page
            imageUrl = self.getImageUrlFromXPath(html, '//div[@id="post_view"]//img')

            # Go through the thumbnails replacing the id of the previous image in the imageUrl on each iteration.
            for i in range(1,imageCount+1):
                imgId = '%02d' % i
                imageUrl = re.sub(r'\d{1,3}.jpg', imgId + '.jpg', imageUrl)
                thumbUrl = None
                if thumbPattern is not None:
                    thumbUrl = re.sub(r'\d{1,3}.jpg', imgId + '.jpg', firstImage)

                if imgCount > sceneImgMax:
                    #self.Log('Maximum background art downloaded')
                    break
                imgCount += 1

                if self.hasProxy():
                    imgUrl = self.makeProxyUrl(imageUrl, firstViewerPageUrl)
                    thumbUrl = None
                else:
                    imgUrl = imageUrl
                    thumbUrl = None

                if not imgUrl in metadata.art.keys() or force:
                    if thumbUrl is not None:
                        self.addTask(queue, self.downloadImage, thumbUrl, imgUrl, firstViewerPageUrl, True, i, sceneIndex, result)
                    else:
                        self.addTask(queue, self.downloadImage, imgUrl, imgUrl, firstViewerPageUrl, False, i, sceneIndex, result)

        if imgCount == 0:
            # Use the player image from the main page as a backup
            playerImg = self.getImageUrlFromXPath(sceneHtml, '//img[@alt="Play this Video" or contains(@src,"/hor.jpg")]')
            if playerImg is not None and len(playerImg) > 0:
                if self.hasProxy():
                    img = self.makeProxyUrl(playerImg, sceneUrl)
                else:
                    img = playerImg

                if not img in metadata.art.keys() or force:
                    self.addTask(queue, self.downloadImage, img, img, sceneUrl, False, 0, sceneIndex, result)



    

    def downloadImage(self, url, referenceUrl, referer, isPreview, index, sceneIndex, results):
        results.append({'url': referenceUrl, 'image': HTTP.Request(url, cacheTime=0, headers={'Referer': referer}, sleep=REQUEST_DELAY).content, 'isPreview': isPreview, 'index': index, 'scene': sceneIndex})

def safe_unicode(s, encoding='utf-8'):
    if s is None:
        return None
    if isinstance(s, basestring):
        if isinstance(s, types.UnicodeType):
            return s
        else:
            return s.decode(encoding)
    else:
        return str(s).decode(encoding)
