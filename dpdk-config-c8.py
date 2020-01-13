import subprocess
import sys
import argparse
import os
import shutil
import re

systemd_tmpl='''[Unit]
Description=DPDK Service
After=network-online.target
Wants=network-online.target

[Service]
%s

[Install]
WantedBy=multi-user.target
'''
_dpdk_unit='/etc/systemd/system/dpdk.service'
_reboot=False
_dpdk_git='https://github.com/DPDK/dpdk.git'

def _exec(cmd):
    return subprocess.call(cmd.split(' '))

def _setup_grub(config):
    global _reboot
    CL='GRUB_CMDLINE_LINUX='
    x86_iommu_on='intel_iommu=on iommu=pt'
    gf_buf = []
    with open('/etc/default/grub', 'r+') as gf:
        for gfl in gf.readlines():
            gfl = gfl.strip()
            if CL in gfl:
                if not x86_iommu_on in gfl:
                    cmdln = gfl.split(CL)[1].replace('"', '')
                    cmdln = '%s"%s %s"'%(CL, x86_iommu_on, cmdln)
                    gfl = cmdln
                    _reboot = True
                if not 'hugepagesz' in gfl and config != None:
                    hpg = 'default_hugepagesz=%s hugepagesz=%s hugepages=%i'%(config['hugepgsz'], config['hugepgsz'],config['nr_hugepgs'])
                    cmdln = gfl.split(CL)[1].replace('"', '')
                    cmdln = '%s"%s %s"'%(CL, hpg, cmdln) 
                    gfl = cmdln
                    _reboot = True
            gf_buf.append(gfl)
        gf.seek(0, 0)
        for ngl in gf_buf:
            gf.write(ngl+"\n")
    _exec('grub2-mkconfig -o /boot/efi/EFI/centos/grub.cfg')
    with open('/proc/cmdline', 'r') as cmdl:
        if not 'x86_iommu_on' in cmdl or not 'hugepagesz' in cmdl:
            _reboot = True

def _setup_driver(driver):
    with open('/etc/modules-load.d/%s.conf'%driver, 'w') as vfmod:
        vfmod.write('%s\n'%driver)
    _exec('modprobe %s'%driver)

def _bind_devs(dl, driver, use_local=True):
    if use_local:
        cmd = "ExecStart=/usr/bin/python3 /usr/local/sbin/dpdk-devbind --bind=%s %s"%(driver, dl)
    else:
        cmd = "ExecStart=/usr/bin/python3 /usr/sbin/dpdk-devbind --bind=%s %s"%(driver, dl)
    systemd_conf = systemd_tmpl%(cmd)
    with open(_dpdk_unit, 'w') as sf:
        sf.write(systemd_conf)
    _exec('systemctl enable dpdk.service')
    _exec('systemctl restart dpdk.service')

def _get_dpdk_src():
    cwd = os.getcwd()
    src = '/tmp/dpdk'
    if os.path.exists(src):
        os.chdir(src)
        _exec('git pull origin master')
    else:
        _exec('git clone %s %s'%(_dpdk_git, src))

def _copy_usertools():
    src = '/tmp/dpdk/usertools/dpdk-devbind.py'
    dst = '/usr/local/sbin/dpdk-devbind'
    if os.path.exists(dst):
        os.remove(dst)
    shutil.copy(src, dst)

def _dnf_install_dpdk():
    _exec('dnf -y install dpdk dpdk-devel dpdk-tools')

def _validate_sizes(sv, _min, _max):
    if sv == None:
        return False
    pattern = '[%i-%i]+(G|g|M|m)$'%(_min, _max)
    if re.search(pattern, sv) == None:
        return False
    else:
        return True

def main():
    global _reboot
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--nics', nargs='*', default=[], help='Space separated list of NICs to be bound to dpdk')
    parser.add_argument('-d', '--driver', type=str, default='vfio-pci', help='Binding dpdk driver')
    parser.add_argument('-s', '--from-src', action='store_true', help='Use source from dpdk git')
    parser.add_argument('--huge-page-size', type=str, help='Huge page size with M/m and G/g suffixes for Mb and Gb values respectively')
    parser.add_argument('--huge-pages', type=int, help='Number of huge page size')
    args = parser.parse_args()

    if args.from_src:
        _get_dpdk_src()
        _copy_usertools()
    else:
        _dnf_install_dpdk()
    cfg = None
    if args.huge_page_size != None  and args.huge_pages != 0: 
        if not _validate_sizes(args.huge_page_size, 1, 4):
            raise ("%s is an invalid huge page size"%args.huge_page_size)
        cfg = {'hugepgsz': args.huge_page_size, 'nr_hugepgs': args.huge_pages}
    _setup_grub(cfg)
    _setup_driver(args.driver)
    _bind_devs(' '.join(args.nics), args.driver, use_local=args.from_src)
    if _reboot:
        _exec('reboot')

if __name__ == "__main__":
    main()
