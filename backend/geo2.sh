#!/bin/fish
#python3 import.py index /home/user/sync/solocator/ /home/user/iot2/html/geo/pics/;
#python3 import.py optimize /home/user/sync/solocator/ /home/user/iot2/html/geo/pics/ $0
python3 import.py process --directory /home/user/iot2/html/geo/pics/ /home/user/sync/solocator/ /home/user/sync/hillview/ $0
