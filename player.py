import logging
import threading
import requests
from enum import Enum
from dataclasses import dataclass

import pafy
import vlc


MAX_HIST = 7
PAFY_MAX_TRIES = 10


logger = logging.getLogger(__name__)


with open('youtube_api_key.secret') as f:
    pafy.set_api_key(f.read().strip())


class Status(Enum):
    STOPPED = "stopped"
    BUFFERING = "buffering"
    PLAYING = "playing"
    PAUSED = "paused"

@dataclass
class NearerSong:
    user: str
    url: str
    title: str
    length: int
    thumb: str


class Player:
    def __init__(self, song_end, status_change):
        """
        song_end: function to call after each song finishes
        status_change: function to call when player starts playing or pauses
        """

        self.status = Status.STOPPED

        self.song_end_callback = song_end
        self.status_change_callback = status_change

        # all_songs is a list of NearerSong's with the most recently added song at the start.
        # When each song ends, all_songs is trimmed so that no more than MAX_HIST already played
        # songs are stored. current_song_idx gives the index of the currently playing song, or -1
        # if all songs have been played. songs_lock should be acquired when modifying all_songs
        # or current_song_idx.
        self.all_songs = []
        self.current_song_idx = -1
        self.songs_lock = threading.Lock()

        # Create a new VLC MediaListPlayer and MediaList.
        self.vlc_instance = vlc.Instance()
        self.vlc_player = self.vlc_instance.media_list_player_new()
        self.vlc_list = self.vlc_instance.media_list_new()
        self.vlc_player.set_media_list(self.vlc_list)

        # Attach functions to player events for when song ends, when playing starts, and when paused.
        # Note: libvlc is not reentrant, so these functions cannot call a libvlc function directly.
        player_events = self.vlc_player.get_media_player().event_manager()
        player_events.event_attach(vlc.EventType.MediaPlayerEndReached, self.song_ended)
        player_events.event_attach(vlc.EventType.MediaPlayerPlaying, self.playing)
        player_events.event_attach(vlc.EventType.MediaPlayerPaused, self.paused)

    def toggle_pause(self):
        logger.info("toggling pause")
        self.vlc_player.pause()

    def next(self):
        """
        Skip the current song.
        If the queue is not already exhausted, increments current_song_idx and
        tells VLC to either go to the next song or stop playing.
        """

        with self.songs_lock:
            # If queue is already exhausted (should be playing nothing) do nothing
            if self.queue_exhausted():
                logger.info("queue is exhausted, ignoring next call")
            else:
                logger.info(f"skipping song {self.current_song_idx}")
                self.current_song_idx -= 1

                if self.queue_exhausted():
                    logger.info("last song was skipped, stopping player")
                    self.vlc_player.stop()
                    self.status = Status.STOPPED
                else:
                    self.vlc_player.next()
                    self.status = Status.BUFFERING

            # Limit number of played songs stored
            self.all_songs = self.all_songs[:self.current_song_idx + MAX_HIST + 1]

    def add_song(self, user, url):
        """
        Get a video from youtube using pafy.
        Add the audio stream url to the VLC MediaList.
        Add a NearerSong with info to all_songs.
        If the queue is exhausted, start playing from this song.
        """

        # Sometimes the stream url gives a 403 error, so check for this before adding it to the queue.
        for i in range(PAFY_MAX_TRIES):
            try:
                video = pafy.new(url)
            except:
                logger.error(f"couldn't get youtube video at {url}")
                raise ValueError(f"couldn't get youtube video at {url}")

            # Make a request to the stream url and check response code.
            logger.info(f"trying to get stream for '{video.title}'")
            best_audio = video.getbestaudio()
            r = requests.get(best_audio.url, stream=True)
            logger.info(f"response code {r.status_code}")

            if r.status_code == 200:
                with self.songs_lock:
                    # Before adding, check if the queue was exhausted. If it was, make a new playlist and start with this song.
                    if self.queue_exhausted():
                        logger.info("queue was exhausted, starting new playlist")
                        self.vlc_list.release()
                        self.vlc_list = self.vlc_instance.media_list_new()
                        self.vlc_player.set_media_list(self.vlc_list)
                        self.vlc_list.add_media(best_audio.url)
                        self.status = Status.BUFFERING
                        self.vlc_player.play()
                    else:
                        self.vlc_list.add_media(best_audio.url)

                    # Add new song to the beginning of all_songs, and increment current_song_idx to match the current song being pushed by 1
                    self.all_songs.insert(0,
                        NearerSong(
                            user,
                            "https://youtu.be/" + video.videoid,
                            video.title,
                            video.length,
                            video.bigthumbhd.replace("http:", "https:")
                        )
                    )
                    self.current_song_idx += 1

                logger.info(f"added '{video.title}'")

                return

        logger.error(f"couldn't get stream for '{video.title}'")
        raise ValueError(f"couldn't get stream for '{video.title}'")

    def song_ended(self, event):
        """
        Callback for VLC MediaPlayerEndReached event.
        Increment current_song_idx and call self.song_end_callback()
        """

        with self.songs_lock:
            logger.info(f"song {self.current_song_idx} ended")
            self.current_song_idx -= 1

            if self.queue_exhausted():
                logger.info("last song finished")
                self.status = Status.STOPPED
            else:
                self.status = Status.BUFFERING

            # Limit number of played songs stored
            self.all_songs = self.all_songs[:self.current_song_idx + MAX_HIST + 1]

        self.song_end_callback()

    def playing(self, event):
        self.status = Status.PLAYING
        self.status_change_callback()

    def paused(self, event):
        self.status = Status.PAUSED
        self.status_change_callback()

    def queue_exhausted(self):
        """
        Check if all songs in all_songs have already played
        """

        return self.current_song_idx <= -1

    def get_progress(self):
        p = self.vlc_player.get_media_player()
        return p.get_time(), p.get_length()
