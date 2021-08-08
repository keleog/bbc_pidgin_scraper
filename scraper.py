import argparse
import csv
import itertools
import logging
import time

import requests
import yaml
from bs4 import BeautifulSoup

logging.root.setLevel(logging.INFO)

ENV = yaml.load(open("env.yml"), Loader=yaml.FullLoader)
ALL_CATEGORIES = ENV["CATEGORY_URLS"]


def get_parser() -> argparse.ArgumentParser:
    """
    parse command line arguments

    returns:
        parser - ArgumentParser object
    """
    parser = argparse.ArgumentParser(description="BBC Pidgin Scraper")
    parser.add_argument(
        "--output_file_name", 
        type=str, 
        default="bbc_pidgin_corpus.csv", 
        help="Name of output file",
        )
    parser.add_argument(
        "--no_of_articles", 
        type=int, 
        default=-1, 
        help="Number of articles to be scraped from the BBC pidgin website"
             "If -1, we scrape all articles we find",
        )
    parser.add_argument(
        "--categories", 
        type = str, 
        default= "all", 
        help= "Specify what news categories to scrape from." 
              "Multiple news categories should be separated by a comma. eg. 'africa,world,sport'",
        )
    
    parser.add_argument(
        "--time_delay", 
        type = bool, 
        default= True, 
        help= "Specify time delay after every url request",
        )
    
    parser.add_argument(
        "--spread",
        action="store_true",
        help="Spread `no_of_articles` evenly across categories"
    )
    
    return parser


def get_page_soup(url:str) -> BeautifulSoup:
    """
    Makes a request to a url and creates a beautiful soup oject from the response html

    input:
        :param url: input page url
    returns:
        - page_soup: beautiful soup oject from the response html
    """

    response = requests.get(url)
    page_html = response.text
    page_soup = BeautifulSoup(page_html, "html.parser")

    return page_soup


def get_urls(category_url:str, category:str, time_delay:bool, articles_per_category: int = None) -> list:
    """
    Obtains all the article urls from the category url it takes in

    input:
        :param categpry_url: category url
        :param category: category name
    returns:
        - category_urls: list of all valid article urls on all the category pages
    """
    page_soup = get_page_soup(category_url)
    category_urls = get_valid_urls(page_soup)

    # get total number of pages for given category
    article_count_span = page_soup.find_all(
        "span", attrs={"class": ENV["ARTICLE_COUNT_SPAN"]}
        )
    # if there are multiple pages, get valid urls from each page
    # else just get the articles on the first page
    if article_count_span:
        total_article_count = int(article_count_span[0].text)
        logging.info(f"{total_article_count} pages found for {category}")
        logging.info(f"{len(category_urls)} urls in page 1 gotten for {category}")

        if articles_per_category and len(category_urls) >= articles_per_category:
                return category_urls

        for count in range(1, total_article_count):

            page_soup = get_page_soup(category_url + f"/page/{count+1}")
            page_urls = get_valid_urls(page_soup)
            logging.info(f"{len(page_urls)} urls in page {count+1} gotten for {category}")
            category_urls+=page_urls
            
            if articles_per_category and len(category_urls) >= articles_per_category:
                break

            if time_delay: 
                time.sleep(10)
    else:
        logging.info(f"Only one page found for {category}. {len(category_urls)} urls gotten")

    return category_urls


def get_valid_urls(category_page:BeautifulSoup) -> list:
    """
    Gets all valid urls from a category page

    input:
        :param: url: category_page
    returns:
        - valid_urls: list of all valid article urls on a given category page
    """
    all_urls = category_page.findAll("a")
    valid_article_urls = []
    for url in all_urls:
        href = url.get("href")
        # from a look at BBC pidgin's urls, they always begin with the following strings. 
        # so we obtain valid article urls using these strings
        if (
            href.startswith("/pidgin/tori") or href.startswith("/pidgin/world") or href.startswith("/pidgin/sport")
            ) and href[-1].isdigit():
            story_url = "https://www.bbc.com" + href
            valid_article_urls.append(story_url)

    return list(set(valid_article_urls))


def get_article_data(article_url:str) -> tuple:
    """
    Obtains paragraphs texts and headlines input url article

    input:
        :param article_url: category_page
    returns:
        - headline: headline of url article 
        - story_text: text of url article
        - article_url: input article url
    """
    page_soup = get_page_soup(article_url)

    headline = page_soup.find(
        "h1", attrs={"class": ENV["HEADLINE_SPAN_CLASS_A"]}
        )
    # by inspection, if the headline is not in the class above, it should be in the one below
    # TODO: Investigate if this is still necessary
    if not headline:
        headline = page_soup.find(
            "strong", attrs={"class": ENV["HEADLINE_SPAN_CLASS_B"]}
            )
    
    if headline:
        headline = headline.text.strip()
    
    story_text = " "
    story_div = page_soup.find_all(
        "div", attrs={"class": ENV["STORY_DIV_CLASS"]}
        )
    if story_div:
        all_paragraphs = [div.findAll("p", recursive=False) for div in story_div]
        all_paragraphs = list(itertools.chain(*all_paragraphs))
        story_text = story_text.join(str(paragraph) for paragraph in all_paragraphs)
        story_text = BeautifulSoup(story_text, "html.parser").get_text()
    story_text = story_text if not story_text == " " else None

    return (headline, story_text, article_url)


def scrape(output_file_name:str, no_of_articles:int, category_urls:dict, time_delay:bool) -> None:
    """
    Main function for scraping and writing articles to file

    input:
        :param output_file_name: file name where output is saved
        :param no_of_articles: number of user specified articles to scrape
        :param category_urls: all articles in a category
    """
    logging.info("Writing articles to file...")

    with open(output_file_name, "w") as csv_file:
        headers = ["headline", "text", "category", "url"]
        writer = csv.DictWriter(csv_file, delimiter="\t", fieldnames = headers)
        writer.writeheader()
        story_num = 0

        for category, urls in category_urls.items():
            logging.info(f"Writing articles for {category} category...")
            for url in urls:
                headline, paragraphs, url = get_article_data(url)
                if paragraphs:
                    writer.writerow({
                        headers[0]:headline, 
                        headers[1]:paragraphs, 
                        headers[2]:category, 
                        headers[3]:url,
                        })
                    story_num+=1
                    logging.info(f"Successfully wrote story number {story_num}")

                if story_num == no_of_articles:
                    logging.info(
                        f"Requested total number of articles {no_of_articles} reached"
                        )
                    logging.info(
                        f"Scraping done. A total of {no_of_articles} articles were scraped!"
                        )
                    return
                if time_delay: 
                    time.sleep(10)
    logging.info(
        f"Scraping done. A total of {story_num} articles were scraped!"
        )


if __name__ == "__main__":

    logging.info("--------------------------------------")
    logging.info("Starting scraping...")
    logging.info("--------------------------------------")

    # initialize parser
    parser = get_parser()
    params, unknown = parser.parse_known_args()

    # specify categories to scrape
    if params.categories != "all":
        categories = params.categories.upper().split(",")
        categories = {category: ALL_CATEGORIES[category] for category in categories}
    else:
        categories = ALL_CATEGORIES

    articles_per_category = None
    if params.no_of_articles > 0 and params.spread:
        if "most_popular" in categories:
            # most_popular only has ne page
            articles_per_category = (params.no_of_articles-10) // (len(categories)-1)
        else:
            articles_per_category = params.no_of_articles // len(categories)
        logging.info(f"Will collect at least {articles_per_category} stories per category")
    
    # get urls
    category_urls = {}
    for category, url in categories.items():
        logging.info(f"Getting stories for {category}...")
        category_story_links = get_urls(url, category, params.time_delay, articles_per_category)
        logging.info(f"{len(category_story_links)} stories found for {category} category")
        category_urls[category] = category_story_links

    # scrape and write to file 
    scrape(params.output_file_name, params.no_of_articles, category_urls, params.time_delay)
