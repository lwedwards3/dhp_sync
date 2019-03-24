#import vpr_sync

#vprs = vpr_sync.VPRSync(auto_mode=False)


#vprs._get_mc_requests()
#vprs._update_requests_from_file()

#vprs.sync_with_wl()
#vprs.send_member_emails()
#vprs._save_requests_to_file()


#vprs.sync_archive()
#vprs.post_logfile()


import wunder_list

wl = wunder_list.WunderList()

'''tasks = wl.get_tasks()
for task in tasks:
    assets = wl.get_task_files(task_id=task['id'])
    print(assets)

'''
preview = wl.get_file_preview(58211092)

#print(preview)

import urllib2

url = preview['url']

#file_name = url.split('/')[-1]
file_name = 'test.jpg'
u = urllib2.urlopen(url)

with open(file_name, 'wb') as f:

    block_sz = 8192
    while True:
        buffer = u.read(block_sz)
        if not buffer:
            break

        f.write(buffer)

print('done')