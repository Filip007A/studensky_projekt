import time
from google.transit import gtfs_realtime_pb2

feed = gtfs_realtime_pb2.FeedMessage()
feed.header.gtfs_realtime_version = "2.0"
feed.header.timestamp = int(time.time())

e = feed.entity.add()
e.id = "test-1"
tu = e.trip_update
tu.trip.trip_id = "trip-1"
tu.trip.route_id = "X"

stu = tu.stop_time_update.add()
stu.stop_id = "stop-1"
stu.arrival.time = int(time.time()) + 120  # 2 minutes from now

with open("/tmp/feed.pb", "wb") as fh:
    fh.write(feed.SerializeToString())

print("Wrote /tmp/feed.pb")