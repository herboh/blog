"""Visitor selections and cached art, using synthetic accounts and history only."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from interests import artwork, enrichment, publish, sources
from interests.storage import connect, get_meta, save_events, set_meta, stable_id

NOW = 1791450000
ART = 'https://lastfm-img.freetls.fastly.net/i/u/300x300/example.jpg'


class ProfileTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = connect(self.root / 'history.sqlite3')
        self.addCleanup(self.db.close)

    def test_films_use_explicit_letterboxd_favorites_and_tv_can_be_pinned(self):
        def event(title, i):
            return dict(id=str(i), occurred=NOW - i, item=stable_id(title), title=title, creator='', image='', url='')
        with self.db:
            set_meta(self.db, 'film_favorites', [dict(title='Favorite film', subtitle='1999', image='', url='')])
            save_events(self.db, 'tautulli', [event('Private movie history', 0)])
            save_events(self.db, 'letterboxd', [event('Recent diary film', 1)])
            save_events(self.db, 'tautulli_tv', [event('New show', 1), *[event('Most played show', i) for i in range(2, 5)]])
        view = publish.export(self.db, ROOT, {'show_picks': [{'title': 'Untracked favorite'}]}, NOW)['profile']
        films, shows = view['watching']
        self.assertEqual(films['items'][0]['title'], 'Favorite film')
        self.assertEqual(films['recent'][0]['title'], 'Recent diary film')
        self.assertNotIn('Private movie history', json.dumps(view))
        self.assertEqual([s['title'] for s in shows['items']], ['Untracked favorite', 'Most played show', 'New show'])
        self.assertEqual(shows['recent'][0]['title'], 'New show')
        self.assertNotIn('occurred', json.dumps(view))
        self.assertNotIn('last_success', json.dumps(view))

    def test_excluded_steam_game_is_absent_from_top_and_recent(self):
        with self.db:
            for app, title in [('10', 'Keep me'), ('20', 'Hide me')]:
                item = dict(appid=app, title=title, minutes=100, recent_minutes=10, image='', url='')
                self.db.execute('INSERT INTO snapshots VALUES (?,?,?,?)', (NOW, app, 100, json.dumps(item)))
        view = publish.export(self.db, ROOT, {'exclude_steam_apps': [20]}, NOW)['profile']
        self.assertIn('Keep me', json.dumps(view))
        self.assertNotIn('Hide me', json.dumps(view))

    def test_failed_enrichment_retains_saved_favorites(self):
        with self.db:
            set_meta(self.db, 'letterboxd', {'failed': False})
            set_meta(self.db, 'film_favorites', [{'title': 'Keep this'}])
        with patch('interests.enrichment.letterboxd_favorites', side_effect=sources.FetchError('Unavailable')):
            enrichment.enrich(self.db, {'LETTERBOXD_USERNAME': 'synthetic'}, 'letterboxd')
        self.assertEqual(get_meta(self.db, 'film_favorites'), [{'title': 'Keep this'}])

    def test_tv_art_fallback_requires_one_exact_match_and_survives_offline(self):
        view = {'profile': {'watching': [{'key': 'shows', 'items': [{'title': 'Series', 'image': ''}], 'recent': []}]}}
        result = [{'show': {'name': 'Series', 'url': 'https://www.tvmaze.com/shows/1/series', 'image': {'medium': 'https://static.tvmaze.com/poster.jpg'}}}]
        with patch('interests.enrichment.fetch', return_value=result):
            enrichment.fill_show_art(self.db, view)
        item = view['profile']['watching'][0]['items'][0]
        self.assertEqual(item['image'], 'https://static.tvmaze.com/poster.jpg')
        self.assertIn('www.tvmaze.com', item['url'])
        item['image'] = ''
        with patch('interests.enrichment.fetch') as network:
            enrichment.fill_show_art(self.db, view, online=False)
            network.assert_not_called()
        self.assertTrue(item['image'])
        item.update(title='Ambiguous', image='')
        result[0]['show']['name'] = 'Ambiguous'
        with patch('interests.enrichment.fetch', return_value=result * 2):
            enrichment.fill_show_art(self.db, view)
        self.assertEqual(item['image'], '')

    def test_artwork_is_local_reused_offline_and_pruned_only_from_public(self):
        item = {'title': 'Album', 'image': ART}
        view = {'profile': {'shelves': [{'items': [item], 'recent': []}]}}
        cache = self.root / '.local/artwork'
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value.read.return_value = b'\xff\xd8\xfftest-image'
        with patch('interests.artwork.urllib.request.build_opener', return_value=opener):
            artwork.cache_public_art(view, cache)
        self.assertTrue(item['image'].startswith('/images/interests/'))
        filename = artwork.poster_name(item['image'])
        self.assertEqual((cache / filename).stat().st_mode & 0o777, 0o600)
        item['image'] = ART
        with patch('interests.artwork.urllib.request.build_opener') as network:
            artwork.cache_public_art(view, cache, online=False)
            network.assert_not_called()
        artwork.publish_posters(view, self.root, cache)
        self.assertTrue((self.root / 'static' / item['image'].lstrip('/')).is_file())
        artwork.prune_posters({'profile': {}}, self.root)
        self.assertTrue((cache / filename).is_file())
        self.assertFalse((self.root / 'static/images/interests' / filename).exists())

    def test_failed_image_is_requested_once_and_not_left_remote(self):
        items = [{'image': ART}, {'image': ART}]
        view = {'profile': {'shelves': [{'items': items, 'recent': []}]}}
        opener = MagicMock()
        opener.open.side_effect = OSError('Unavailable')
        with patch('interests.artwork.urllib.request.build_opener', return_value=opener):
            artwork.cache_public_art(view, self.root / 'artwork')
        self.assertEqual(opener.open.call_count, 1)
        self.assertEqual([i['image'] for i in items], ['', ''])


class SelectionProviderTest(unittest.TestCase):
    def test_lastfm_actual_cdn_allowed_but_placeholder_and_credentials_rejected(self):
        self.assertEqual(sources.image_url(ART), ART)
        self.assertEqual(sources.image_url(ART.replace('example', '2a96cbd8b46e442fc41c2b86b821562f')), '')
        self.assertEqual(sources.image_url(ART.replace('https://', 'https://secret@')), '')

    def test_music_all_time_ranking_is_independent_of_partial_scrobble_history(self):
        def reply(env, method, **params):
            self.assertEqual(params['period'], 'overall')
            if method == 'user.gettopalbums':
                return {'topalbums': {'album': [{'name': 'Classic', 'artist': {'name': 'All-time artist'}, 'image': [{'#text': ART}]}]}}
            return {'topartists': {'artist': [{'name': 'All-time artist'}]}}
        recent = [{'creator': 'New obsession', 'album': 'New record', 'image': ART}]
        with patch('interests.enrichment.lastfm_call', side_effect=reply):
            selection = enrichment.music_selection({}, recent)
        self.assertEqual(selection['artists'][0]['title'], 'All-time artist')
        self.assertEqual(selection['artists'][0]['subtitle'], 'Classic')
        self.assertEqual(selection['recent'][0]['title'], 'New obsession')

    def test_letterboxd_favorites_parse_separately_from_other_posters(self):
        profile = '''<div data-component-class="LazyPoster" data-item-name="Not a favorite (2020)" data-item-link="/film/other/"></div>
        <section id="favourites"><div data-component-class="LazyPoster" data-item-name="A Favorite (1999)" data-item-link="/film/a-favorite/"></div></section>'''
        film = '''<script type="application/ld+json">/* <![CDATA[ */{"@type":"Movie","image":"https://a.ltrbxd.com/poster.jpg"}/* ]]> */</script>'''
        with patch('interests.enrichment.fetch', side_effect=[profile, film]):
            items = enrichment.letterboxd_favorites({'LETTERBOXD_USERNAME': 'synthetic'}, [])
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]['title'], 'A Favorite')
        self.assertEqual(items[0]['image'], 'https://a.ltrbxd.com/poster.jpg')
        self.assertNotIn('synthetic', json.dumps(items))
        with patch('interests.enrichment.fetch', return_value='<html>Unexpected markup</html>'):
            with self.assertRaises(sources.FetchError):
                enrichment.letterboxd_favorites({'LETTERBOXD_USERNAME': 'synthetic'}, items)

    def test_unavailable_film_art_does_not_discard_favorites(self):
        html = '<section id="favourites"><div data-component-class="LazyPoster" data-item-name="Favorite (2000)" data-item-link="/film/favorite/"></div></section>'
        with patch('interests.enrichment.fetch', side_effect=sources.FetchError('HTTP 403')):
            items = enrichment.favorites_from_html(html, [])
        self.assertEqual(items[0]['title'], 'Favorite')
        self.assertEqual(items[0]['image'], '')

    def test_tv_episodes_group_under_show_and_reject_unfiltered_movies(self):
        row = dict(user_id=12, media_type='episode', stopped=NOW, percent_complete=95,
                   row_id=1, reference_id=1, title='Episode title', grandparent_title='Series title', grandparent_rating_key='77')
        reply = {'response': {'result': 'success', 'data': {'data': [row], 'recordsFiltered': 1}}}
        env = dict(TAUTULLI_URL='http://localhost:8181', TAUTULLI_USER_ID='12', TAUTULLI_API_KEY='secret')
        with patch('interests.sources.fetch', return_value=reply) as fetch:
            events, _ = sources.tautulli_tv(env, {}, NOW, 2)
            self.assertEqual(fetch.call_args.args[1]['media_type'], 'episode')
        self.assertEqual(events[0]['title'], 'Series title')
        self.assertEqual(events[0]['poster_key'], '77')
        row['media_type'] = 'movie'
        with patch('interests.sources.fetch', return_value=reply):
            with self.assertRaises(sources.FetchError):
                sources.tautulli_tv(env, {}, NOW, 2)
