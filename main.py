#!/bin/env python3
from psycopg2.extras import DictCursor
import sys
import configparser
import psycopg2
import json
import os.path
import datetime


class GalleryAlbum:

    def __init__(self, **kwargs):
        album_cols = ['id', 'title', 'user_name', 'user_fullname', 'user_email', 'filename', 'parent_id']
        self.__dict__.update((k, v) for k, v in kwargs.items() if k in album_cols)


class GalleryArt:

    def __init__(self, **kwargs):
        art_cols = ['id', 'title', 'description', 'summary', 'user_name', 'user_fullname',
                    'user_email', 'filename', 'mimetype', 'filesize', 'parent_id']
        self.__dict__.update((k, v) for k, v in kwargs.items() if k in art_cols)


def db_connect(config):
    conn = psycopg2.connect(f'host={config["default"]["DB_HOST"]} dbname={config["default"]["DB_NAME"]} '
                            f'user={config["default"]["DB_USER"]} password={config["default"]["DB_PASS"]}')
    return conn


def get_data(dbcon):
    cur = dbcon.cursor(cursor_factory=DictCursor)

    album_query = """
SELECT 
    i.g_id AS id,
    i.g_title AS title,
    u.g_username AS user_name,
    u.g_fullname AS user_fullname,
    u.g_email AS user_email, 
    f.g_pathcomponent AS filename, 
    c.g_parentid AS parent_id
FROM g2_item i, g2_user u, g2_filesystementity f, g2_childentity c 
WHERE i.g_ownerid = u.g_id 
AND i.g_id = f.g_id
AND i.g_id = c.g_id    
AND i.g_cancontainchildren > 0
"""
    cur.execute(album_query)
    album_records = cur.fetchall()
    albums = [GalleryAlbum(**dict(row)) for row in album_records]

    art_query = """
SELECT
    i.g_id AS id,  
    i.g_title AS title, 
    i.g_description AS description, 
    i.g_summary AS summary, 
    u.g_username AS user_name,
    u.g_fullname AS user_fullname,
    u.g_email AS user_email, 
    f.g_pathcomponent AS filename, 
    d.g_mimetype AS mimetype, 
    d.g_size AS filesize,
    c.g_parentid AS parent_id
FROM g2_item i, g2_user u, g2_filesystementity f, g2_dataitem d, g2_childentity c 
WHERE i.g_ownerid = u.g_id 
AND i.g_id = f.g_id
AND i.g_id = d.g_id
AND i.g_id = c.g_id
    """
    cur.execute(art_query)

    art_records = cur.fetchall()
    art = [GalleryArt(**dict(row)) for row in art_records]

    return albums, art


def album_parent_hierachy(albums, album_id):
    """
    Generate a list of all parent albums of the supplied album id
    :return: ordered list beginning with the top-most parent album
    """
    hierachy = []

    prev_album = next(a for a in albums if a.id == album_id)
    try:
        while prev_album.id != 0 and prev_album.filename is not None:
            hierachy.insert(0, prev_album)
            prev_album = next(a for a in albums if a.id == prev_album.parent_id)
    except StopIteration as e:
        ...

    return hierachy


def album_children(album_id, albums):
    """
    Generate list of all album children directly stemming from the supplied album id
    :return: list of all child albums
    """

    return [album for album in albums if album.parent_id == album_id]


def album_to_dict(album, albums, art):
    parent_albums = album_parent_hierachy(albums, album.id)
    child_albums = album_children(album.id, albums)
    album_art = [a for a in art if a.parent_id == album.id]
    data = {
        'id': album.id,
        'title': album.title,
        'filename': album.filename,
        'filepath': '/'.join([a.filename for a in parent_albums]),
        'owner': {
            'username': album.user_name,
            'fullname': album.user_fullname,
            'email': album.user_email
        },
        'children': [],
        'art': [],
    }
    for child in child_albums:
        data['children'].append(album_to_dict(child, albums, art))
    for art in album_art:
        data['art'].append(art_to_dict(art, albums, include_albums=False))

    return data


def build_album_dict(albums, art):
    data = {'albums': []}

    # find root album, it's the one with no parent
    root = next(a for a in albums if a.parent_id == 0)
    data['albums'].append(album_to_dict(root, albums, art))

    return data


def art_to_dict(item, albums, include_albums=True):
    item_albums = album_parent_hierachy(albums, item.parent_id)
    data = {
        'id': item.id,
        'title': item.title,
        'summary': item.summary,
        'description': item.description,
        'filename': item.filename,
        'filepath': '/'.join([album.filename for album in item_albums] + [item.filename]),
        'filesize': item.filesize,
        'mimetype': item.mimetype,
        'owner': {
            'username': item.user_name,
            'fullname': item.user_fullname,
            'email': item.user_email
        },
        'albums': [
            {'name': album.title, 'dir_name': album.filename} for album in item_albums if include_albums
        ]
    }
    return data


def build_art_dict(albums, art):
    data = {'art': []}
    for item in art:
        data['art'].append(art_to_dict(item, albums))
    return data


def build_album_path(albums, album_id):
    parent_albums = album_parent_hierachy(albums, album_id)
    albumpath = '/'.join([f'{a.filename}-{a.id}' for a in parent_albums])
    return albumpath


def build_header(title, tags, category, summary, authors='', toc_run='false'):
    # hard coding html like its 1999!
    return f'''
<html>
<head>
  <title>{title}</title>
  <meta name="tags" content="{tags}" />                                                                                                                                                 
  <meta name="date" content="{datetime.datetime.now():%Y-%m-%d %H:%M:%S}" />
  <meta name="category" content="{category}" />
  <meta name="authors" content="{authors}" />
  <meta name="summary" content="{summary}" />                                                                                               
  <meta name="toc_run" content="{toc_run}" />
</head>
<body>

<!--BEGIN CONTENT-->
    '''


def build_footer():
    return '''
<!--END CONTENT-->
</body>
</html>
    '''


def build_site(albums, art, html_dir='.', art_dir='albums', thumbs_dir='thumbs'):
    # find root album, it's the one with no parent
    root = next(a for a in albums if a.parent_id == 0)
    build_album_page(albums, art, root, html_dir, art_dir, thumbs_dir)


def build_album_page(albums, art, album, html_dir='.', art_dir='albums', thumbs_dir='thumbs', breadcrumbs=[]):
    parent_albums = album_parent_hierachy(albums, album.id)[:-1]
    child_albums = album_children(album.id, albums)
    # sort them alphabetically, make it nice!
    child_albums.sort(key=lambda x: x.title)

    album_art = [a for a in art if a.parent_id == album.id]
    items_per_row = 4

    if not album.filename:
        html_file = os.path.join(html_dir, 'index.html')
    else:
        albumpath = build_album_path(albums, album.id)
        albumdir = os.path.join(html_dir, albumpath)
        try:
            os.makedirs(albumdir)
        except FileExistsError:
            pass
        html_file = os.path.join(albumdir, f'index.html')

    with open(html_file, mode='w', encoding='utf8') as f:
        hdr = build_header(tags='artwork, album', category='art', summary=f'Album artwork: {album.title}',
                           title=f'Album artwork: {album.title}')
        ftr = build_footer()
        print(hdr, file=f)

        breadcrumb_link = '<p>Go Back: '
        home_back = '../' * (len(parent_albums)+1)
        breadcrumb_link += f'<a href="{home_back}index.html">Home</a> '
        for i in range(0,len(parent_albums)):
            j = len(parent_albums) - i
            breadcrumb_back = '../' * j
            breadcrumb_link += f' / <a href="{breadcrumb_back}index.html">{parent_albums[i].title}</a>'
        # for b in breadcrumbs:
        #     breadcrumb_link += f' / <a href="">{b[1]}</a>'
        breadcrumb_link += '</p>'
        print(breadcrumb_link, file=f)

        print('<h3>Sub-folders</h3>', file=f)
        print('<ul>', file=f)
        for c in child_albums:
            print(f'<li><a href="{c.filename}-{c.id}/index.html">{c.title}</a></li>', file=f)
        print('</ul>', file=f)

        print('<h3>Artwork</h3>', file=f)
        print('<table border=0>', file=f)
        for item in album_art:
            item_albums = album_parent_hierachy(albums, item.parent_id)
            art_path = '/'.join([art_dir] + [album.filename for album in item_albums] + [item.filename])
            thumb_path = '/'.join([thumbs_dir] + [album.filename for album in item_albums] + [item.filename])

            print('<tr>', file=f)
            print(f'<td><a href="{art_path}"><img src="{thumb_path}" /></a></td>', file=f)
            print(f'<td>', file=f)
            print(f'<b>Title</b>: {item.title}<br/>', file=f)
            print(f'<b>Submitter</b>: {item.user_name}<br/>', file=f)
            if item.summary and item.summary is not 'None':
                print(f'<b>Summary</b>: {item.summary}<br/>', file=f)
            if item.description and item.description is not 'None':
                print(f'<b>Description</b>: {item.description}<br/>', file=f)
            print(f'</td>', file=f)
            print(f'</tr>', file=f)

        print('</table>', file=f)
        print(ftr, file=f)

    for c in child_albums:
        build_album_page(albums, art, c, html_dir, art_dir, thumbs_dir)


def main():
    if not os.path.exists('config.ini'):
        print('Configuration file config.ini not found.')
        sys.exit(1)

    config = configparser.ConfigParser()
    config.read('config.ini')

    with db_connect(config) as dbcon:
        albums, art = get_data(dbcon)

        art_dict = build_art_dict(albums, art)
        json_data = json.dumps(art_dict, indent=4, ensure_ascii=False)
        with open('art.json', mode='w', encoding='utf8') as f:
            print(json_data, file=f)

        album_dict = build_album_dict(albums, art)
        json_data = json.dumps(album_dict, indent=4, ensure_ascii=False)
        with open('art_by_album.json', mode='w', encoding='utf8') as f:
            print(json_data, file=f)

        build_site(albums, art, html_dir=config['site']['html_dir'],
                   art_dir=config['site']['art_dir'],
                   thumbs_dir=config['site']['thumbs_dir'])


if __name__ == '__main__':
    main()
