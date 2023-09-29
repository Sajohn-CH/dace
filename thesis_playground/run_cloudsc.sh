cloudsc_path='/users/msamuel/dwarf-p-cloudsc-dace'
dace_signature_file='full_cloudsc_logs/signature_dace_cloudscexp4.txt'
cloudsc_version=4
dacecache_folder=".dacecache/CLOUDSCOUTER${cloudsc_version}"
# Read size of NBLOCKS from generated code
NBLOCKS=$(grep "NBLOCKS = " "$dacecache_folder/src/cpu/CLOUDSCOUTER${cloudsc_version}.cpp" | head -n1 | cut -d'=' -f2 | xargs)
#Remove semicolon at the end
NBLOCKS=${NBLOCKS::-1}
repetitions=1
echo "NBLOCKS=$NBLOCKS"

result_dir=$PWD
result_path="$result_dir/result.out"
if [ "$#" -gt 1 ]; then
    if [[ "$1" = /* ]]; then
        result_path="$1"
    else
        result_path="$result_dir/$1"
    fi
    if [ "$#" -eq 2 ]; then
        repetitions=$2
    fi
fi


echo "Build dacecache folder"
cd "$dacecache_folder/build"
sh cmake_configure.sh
make clean && make
cd -

echo "Using signature file at $dace_signature_file"

parameters=$(
    cat $dace_signature_file |
    tr ',' '\n' |
    rev | cut -d ' ' -f1 | rev | 
    tr "\n" "," )
        # | sed --expression="s/%/\&\n,\&/g")
# remove last comma
parameters=${parameters::-1}
# echo $parameters
# put parameter names inside the fortran driver file
sed "s/<signature>/$parameters\&/g" "$cloudsc_path/src/cloudsc_fortran/cloudsc_driver_mod.F90.template" \
    > "$cloudsc_path/src/cloudsc_fortran/cloudsc_driver_mod.F90"

# create parameter list where all parameters are points
# cat $dace_signature_file
# echo ""
parameters_scalar=$(cat $dace_signature_file | grep -oE "(int|double) [a-Z0-9_]+(, )?")
parameters_array=$(cat $dace_signature_file | grep -oE "(int|double) \* __restrict__ [a-Z0-9_]+(, )?")
# echo "$parameters_scalar"
# echo "Parametrers array"
# echo "$parameters_array"
parameters_pointer=$(echo $parameters_scalar |
    sed --expression='s/double/double \*/g' |
    sed --expression='s/int/int \*/g')
parameters_pointer=$(echo "$parameters_array $parameters_pointer")
# echo "$parameters_pointer"
parameters_dereference=$(echo $parameters_scalar |
    sed --expression='s/int /\*/g' |
    sed --expression='s/double /\*/g')
# echo "$parameters_dereference"
parameters_array_names=$(echo "$parameters_array" | cut -d ' ' -f 4)
# echo "Paramters array names"
# echo "$parameters_array_names"
parameters_dereference=$(echo "$parameters_array_names $parameters_dereference")
# echo "$parameters_dereference"


adapter_file="$cloudsc_path/src/cloudsc_fortran/working.cc"
echo "#include <cstdlib>" > $adapter_file 
echo "#include <dace/dace.h>" >> $adapter_file
echo "#include <chrono>" >> $adapter_file
echo "typedef void * CLOUDSCOUTER${cloudsc_version}Handle_t;" >> $adapter_file
echo "extern \"C\" CLOUDSCOUTER${cloudsc_version}Handle_t __dace_init_CLOUDSCOUTER${cloudsc_version}();" >> $adapter_file
echo "extern \"C\" void __dace_exit_CLOUDSCOUTER${cloudsc_version}(CLOUDSCOUTER${cloudsc_version}Handle_t handle);" >> $adapter_file
echo "extern \"C\" void __program_CLOUDSCOUTER${cloudsc_version}(CLOUDSCOUTER${cloudsc_version}Handle_t handle, $(cat $dace_signature_file));" >> $adapter_file
echo "" >> $adapter_file
echo "void cloudsc2_internal($(cat $dace_signature_file))" >> $adapter_file
echo "{" >> $adapter_file
echo "    CLOUDSCOUTER${cloudsc_version}Handle_t handle;" >> $adapter_file
echo "    handle = __dace_init_CLOUDSCOUTER${cloudsc_version}();" >> $adapter_file
echo "    auto start = std::chrono::high_resolution_clock::now();" >> $adapter_file
echo "    __program_CLOUDSCOUTER${cloudsc_version}(handle, $parameters);" >> $adapter_file
echo "    auto end = std::chrono::high_resolution_clock::now();" >> $adapter_file
echo "    printf(\"Time %d [ms]\n\", std::chrono::duration_cast<std::chrono::milliseconds>(end-start).count());" >> $adapter_file
echo "    __dace_exit_CLOUDSCOUTER${cloudsc_version}(handle);" >>  $adapter_file
echo "}" >> $adapter_file
echo "DACE_EXPORTED void cloudsc2_($parameters_pointer)" >> $adapter_file
echo "{" >> $adapter_file
echo "    cloudsc2_internal($parameters_dereference);" >> $adapter_file
echo "}" >> $adapter_file



current_dir=$PWD
cd "$cloudsc_path/build"
echo "Run for $repetitions time"
for i in $(seq 1 $repetitions); do
    echo "run $i"
    make && OMP_NUM_THREADS=1 ./bin/dwarf-cloudsc-fortran 1 $NBLOCKS 1 > "$result_path.${i}"
    cat "$result_path.${i}"
done
cd $current_dir
echo "Saved result into $result_path"
