import logging
import requests
from enum import Enum
from dataclasses import dataclass

import pafy
import vlc


MAX_HIST = 7
PAFY_MAX_TRIES = 10


logger = logging.getLogger(__name__)


pafy.set_api_key('AIzaSyAosU-NtYX-li_SqpcsKfZ4yFoW8SC-fSU')


class Status(Enum):
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"

@dataclass
class NearerSong:
    url: str
    title: str
    length: int
    thumb: str
    thumb_big: str


class Player:
    def __init__(self, song_end):
        """
        song_end: function to call after each song finishes
        """

        self.status = Status.STOPPED

        self.song_end_callback = song_end

        self.all_songs = []
        self.current_song_idx = -1

        # Create a new VLC MediaListPlayer and MediaList.
        vlc_instance = vlc.Instance()
        self.vlc_player = vlc_instance.media_list_player_new()
        self.vlc_list = vlc_instance.media_list_new()
        self.vlc_player.set_media_list(self.vlc_list)

        # Attach self.song_ended to the end reached event for the player.
        # Note: libvlc is not reentrant, so self.song_ended cannot call a libvlc function directly
        player_events = self.vlc_player.get_media_player().event_manager()
        player_events.event_attach(vlc.EventType.MediaPlayerEndReached, self.song_ended)

    def toggle_pause(self):
        logger.info("toggling pause")
        self.vlc_player.pause()

        if self.status == Status.PLAYING: self.status = Status.PAUSED
        elif self.status == Status.PAUSED: self.status = Status.PLAYING

    def next(self):
        """
        Skip the current song.
        If the queue is not already exhausted, increments current_song_idx and
        tells VLC to either go to the next song or stop playing.
        """

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

    def add_song(self, url):
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
            except ValueError:
                logger.error(f"couldn't get youtube video at {url}")
                raise ValueError(f"couldn't get youtube video at {url}")

            logger.info(f"trying to get stream for '{video.title}'")
            best_audio = video.getbestaudio()
            r = requests.get(best_audio.url, stream=True)

            if r.status_code == 200:
                self.vlc_list.add_media(best_audio.url)

                # Before adding to all_songs, check if the queue was exhausted. If it was, start playing this song.
                if self.queue_exhausted():
                    # Use play_item_at_index() because if the player had stopped calling play() would make it start from the beginning.
                    self.vlc_player.play_item_at_index(len(self.all_songs))
                    self.status = Status.PLAYING

                # Add new song to the beginning of all_songs, and increment current_song_idx to match the current song being pushed by 1
                self.all_songs.insert(0, NearerSong(url, video.title, video.length, video.thumb, video.bigthumbhd))
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

        logger.info(f"song {self.current_song_idx} of {len(self.all_songs)} finished")
        self.current_song_idx -= 1

        if self.queue_exhausted():
            self.status = Status.STOPPED

        # Limit number of played songs stored
        self.all_songs = self.all_songs[:self.current_song_idx + MAX_HIST + 1]

        self.song_end_callback()

    def queue_exhausted(self):
        """
        Check if all songs in all_songs have already played
        """

        return self.current_song_idx <= -1
