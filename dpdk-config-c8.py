import subprocess
import sys
import argparse
import os
import shutil

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
_reboot=True
_dpdk_git='https://github.com/DPDK/dpdk.git'

def _exec(cmd):
    return subprocess.call(cmd.split(' '))

def _setup_grub():
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
                else:
                    _reboot=False
            gf_buf.append(gfl)
        gf.seek(0, 0)
        for ngl in gf_buf:
            gf.write(ngl+"\n")
    _exec('grub2-mkconfig -o /boot/efi/EFI/centos/grub.cfg')

def _setup_driver(driver):
    with open('/etc/modules-load.d/%s.conf'%driver, 'w') as vfmod:
        vfmod.write('%s\n'%driver)
    _exec('modprobe %s'%driver)

def _bind_devs(dl, driver):
    cmd = "ExecStart=/usr/bin/python3 /usr/local/bin/dpdk/usertools/dpdk-devbind.py --bind=%s %s"%(driver, dl)
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
    src = '/tmp/dpdk/usertools'
    dst = '/usr/local/bin/dpdk'
    if not os.path.exists(dst):
        os.makedirs(dst)
    else:
        shutil.rmtree(dst)
    shutil.copytree(src, '%s/usertools'%dst)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-n', '--nics', nargs='*', default=[], help='Space separated list of NICs to be bound to dpdk')
    parser.add_argument('-d', '--driver', type=str, default='vfio-pci', help='Binding dpdk driver')
    args = parser.parse_args()

    _get_dpdk_src()
    _copy_usertools()
    _setup_grub()
    _setup_driver(args.driver)
    _bind_devs(' '.join(args.nics), args.driver)
    if _reboot:
        _exec('reboot')

if __name__ == "__main__":
    main()
